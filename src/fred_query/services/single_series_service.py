from __future__ import annotations

from datetime import date, timedelta

from fred_query.schemas.analysis import (
    AnalysisResult,
    DerivedMetric,
    HistoricalSeriesContext,
    QueryIntent,
    QueryResponse,
    SeriesAnalysis,
)
from fred_query.services.answer_service import AnswerService
from fred_query.services.chart_service import ChartService
from fred_query.services.fred_client import FREDClient
from fred_query.services.resolver_service import ResolverService
from fred_query.schemas.intent import TransformType
from fred_query.services.transform_service import TransformService


class SingleSeriesLookupService:
    """Deterministic single-series lookup based on a FRED series ID or search phrase."""

    _HISTORICAL_LOOKBACK_YEARS = 50

    def __init__(
        self,
        fred_client: FREDClient,
        *,
        resolver_service: ResolverService | None = None,
        transform_service: TransformService | None = None,
        chart_service: ChartService | None = None,
        answer_service: AnswerService | None = None,
    ) -> None:
        self.fred_client = fred_client
        self.resolver_service = resolver_service or ResolverService(fred_client)
        self.transform_service = transform_service or TransformService()
        self.chart_service = chart_service or ChartService()
        self.answer_service = answer_service or AnswerService()

    @staticmethod
    def _default_start_date() -> date:
        return date.today() - timedelta(days=365 * 10)

    @staticmethod
    def _subtract_years(value: date, *, years: int) -> date:
        try:
            return value.replace(year=value.year - years)
        except ValueError:
            return value.replace(month=2, day=28, year=value.year - years)

    @classmethod
    def _historical_start_date(cls, *, start_date: date, latest_date: date) -> date:
        return min(start_date, cls._subtract_years(latest_date, years=cls._HISTORICAL_LOOKBACK_YEARS))

    @staticmethod
    def _metric_unit_for_series(units: str | None) -> str | None:
        normalized = (units or "").strip().lower()
        if "percent" in normalized:
            return "%"
        if "basis point" in normalized or normalized == "bps":
            return "bps"
        return None

    @classmethod
    def _historical_metrics(
        cls,
        *,
        units: str | None,
        context: HistoricalSeriesContext | None,
    ) -> list[DerivedMetric]:
        if context is None or context.observation_count < 2:
            return []

        metric_unit = cls._metric_unit_for_series(units)
        metrics: list[DerivedMetric] = []
        if context.average_value is not None:
            metrics.append(
                DerivedMetric(
                    name="historical_average",
                    value=round(context.average_value, 4),
                    unit=metric_unit,
                    description=(
                        f"Average across {context.observation_count} observations from "
                        f"{context.start_date.isoformat()} to {context.end_date.isoformat()}."
                    ),
                )
            )
        if context.percentile_rank is not None:
            metrics.append(
                DerivedMetric(
                    name="historical_percentile_rank",
                    value=round(context.percentile_rank, 1),
                    description="Latest reading's percentile rank within the extended history window.",
                )
            )
        if context.max_value is not None and context.max_date is not None:
            metrics.append(
                DerivedMetric(
                    name="historical_peak",
                    value=round(context.max_value, 4),
                    unit=metric_unit,
                    description=(
                        f"Highest observation in the extended window, reached on {context.max_date.isoformat()}."
                    ),
                )
            )
        if context.min_value is not None and context.min_date is not None:
            metrics.append(
                DerivedMetric(
                    name="historical_trough",
                    value=round(context.min_value, 4),
                    unit=metric_unit,
                    description=(
                        f"Lowest observation in the extended window, reached on {context.min_date.isoformat()}."
                    ),
                )
            )
        return metrics

    def lookup(self, intent: QueryIntent) -> QueryResponse:
        response_intent = intent.model_copy(deep=True)
        start_date = intent.start_date or self._default_start_date()
        end_date = intent.end_date
        effective_transform = (
            TransformType.LEVEL if intent.transform == TransformType.NORMALIZED_INDEX else intent.transform
        )
        normalize_chart = intent.normalization or intent.transform == TransformType.NORMALIZED_INDEX

        search_text = intent.search_text or " ".join(intent.indicators)
        resolved_series, metadata, search_match = self.resolver_service.resolve_series(
            explicit_series_id=intent.series_id,
            search_text=search_text,
            geography=intent.geographies[0].name if intent.geographies else "Unspecified",
            indicator=intent.indicators[0] if intent.indicators else "unknown_indicator",
        )
        response_intent.series_id = metadata.series_id
        if not response_intent.search_text:
            response_intent.search_text = search_match.title if search_match is not None else metadata.title
        if not response_intent.indicators:
            response_intent.indicators = [resolved_series.indicator]

        periods_per_year = self.transform_service.periods_per_year_for_frequency(metadata.frequency)
        transform_window, transform_warnings = self.transform_service.resolve_transform_window(
            transform=effective_transform,
            frequency=metadata.frequency,
            requested_window=intent.transform_window,
        )
        warmup_periods = self.transform_service.transform_warmup_periods(
            transform=effective_transform,
            periods_per_year=periods_per_year,
            window=transform_window,
        )
        fetch_start_date = self.transform_service.subtract_periods(
            start_date,
            periods=warmup_periods,
            frequency=metadata.frequency,
        )

        observations = self.resolver_service.get_required_observations(
            metadata.series_id,
            start_date=fetch_start_date,
            end_date=end_date,
        )

        warnings: list[str] = []
        warnings.extend(transform_warnings)
        historical_context = None
        historical_metrics: list[DerivedMetric] = []
        visible_observations = self.transform_service.filter_observations_by_date(
            observations,
            start_date=start_date,
            end_date=end_date,
        )
        if not visible_observations:
            raise ValueError(f"No observations returned for {metadata.series_id} in the requested display window.")

        normalized_observations = None
        transformed_observations = None
        analysis_basis = None
        analysis_units = None
        total_growth = None

        if effective_transform == TransformType.LEVEL:
            normalized_observations = (
                self.transform_service.normalize_to_index(visible_observations) if normalize_chart else None
            )
            latest_value, latest_date = self.transform_service.latest_value(visible_observations)
            total_growth = self.transform_service.calculate_total_growth_pct(visible_observations)
            comparison_units = metadata.units
            compare_on_transformed_series = False
        else:
            transform_result = self.transform_service.apply_single_series_transform(
                observations,
                transform=effective_transform,
                units=metadata.units,
                frequency=metadata.frequency,
                window=transform_window,
            )
            transformed_observations = self.transform_service.filter_observations_by_date(
                transform_result.observations or [],
                start_date=start_date,
                end_date=end_date,
            )
            if not transformed_observations:
                basis_label = transform_result.basis or effective_transform.value.replace("_", " ")
                raise ValueError(f"I could not derive {basis_label} over the requested date range.")

            analysis_basis = transform_result.basis
            analysis_units = transform_result.units
            latest_value, latest_date = self.transform_service.latest_value(transformed_observations)
            comparison_units = analysis_units
            compare_on_transformed_series = transform_result.compare_on_transformed_series

        historical_observations = observations
        if latest_date is not None:
            historical_start = self._historical_start_date(start_date=start_date, latest_date=latest_date)
            historical_fetch_start = historical_start
            if compare_on_transformed_series:
                historical_fetch_start = self.transform_service.subtract_periods(
                    historical_start,
                    periods=warmup_periods,
                    frequency=metadata.frequency,
                )
            try:
                historical_observations = self.resolver_service.get_required_observations(
                    metadata.series_id,
                    start_date=historical_fetch_start,
                    end_date=latest_date,
                )
            except Exception:
                historical_observations = observations
                if historical_fetch_start < observations[0].date:
                    warnings.append(
                        "Extended historical context was unavailable, so comparisons use only the requested range."
                    )

        historical_series = self.transform_service.filter_observations_by_date(
            historical_observations,
            start_date=historical_start if latest_date is not None else start_date,
            end_date=latest_date,
        )
        if compare_on_transformed_series:
            transformed_history = self.transform_service.apply_single_series_transform(
                historical_observations,
                transform=effective_transform,
                units=metadata.units,
                frequency=metadata.frequency,
                window=transform_window,
            )
            history_basis = self.transform_service.filter_observations_by_date(
                transformed_history.observations or [],
                start_date=historical_start if latest_date is not None else start_date,
                end_date=latest_date,
            )
            if history_basis:
                historical_series = history_basis
            else:
                warnings.append(
                    "Historical transform context could not be derived cleanly, so context uses only the requested display window."
                )
                historical_series = transformed_observations or visible_observations

        historical_context = self.transform_service.summarize_historical_context(historical_series)
        historical_metrics = self._historical_metrics(
            units=comparison_units,
            context=historical_context,
        )

        recession_periods = []
        try:
            recession_observations = self.fred_client.get_series_observations(
                "USREC",
                start_date=visible_observations[0].date,
                end_date=visible_observations[-1].date,
            )
            recession_periods = self.transform_service.derive_recession_periods(recession_observations)
        except Exception:
            recession_periods = []

        series_analysis = SeriesAnalysis(
            series=resolved_series,
            observations=visible_observations,
            transformed_observations=transformed_observations or normalized_observations,
            historical_context=historical_context,
            analysis_basis=analysis_basis,
            analysis_units=analysis_units,
            total_growth_pct=total_growth,
            compound_annual_growth_rate_pct=(
                self.transform_service.calculate_cagr_pct(visible_observations)
                if effective_transform == TransformType.LEVEL
                else None
            ),
            latest_value=latest_value,
            latest_observation_date=latest_date,
        )
        derived_metrics = [
            DerivedMetric(
                name="top_search_match",
                value=search_match.series_id if search_match is not None else metadata.series_id,
                description="The series selected for execution.",
            )
        ]
        if analysis_basis:
            derived_metrics.append(
                DerivedMetric(
                    name="analysis_basis",
                    value=analysis_basis,
                    description="Transformation applied before charting and historical comparison.",
                )
            )
        if transform_window is not None and effective_transform in (
            TransformType.ROLLING_AVERAGE,
            TransformType.ROLLING_STDDEV,
            TransformType.ROLLING_VOLATILITY,
        ):
            derived_metrics.append(
                DerivedMetric(
                    name="applied_transform_window",
                    value=transform_window,
                    unit="observations",
                    description="Rolling window length used for the displayed transform.",
                )
            )
        analysis = AnalysisResult(
            series_results=[series_analysis],
            derived_metrics=derived_metrics + historical_metrics,
            warnings=warnings,
            latest_observation_date=latest_date,
            coverage_start=(
                (transformed_observations or visible_observations or normalized_observations)[0].date
            ),
            coverage_end=(
                (transformed_observations or visible_observations or normalized_observations)[-1].date
            ),
        )
        chart = self.chart_service.build_single_series_chart(
            series_result=series_analysis,
            start_year=analysis.coverage_start.year if analysis.coverage_start else visible_observations[0].date.year,
            end_year=analysis.coverage_end.year if analysis.coverage_end else visible_observations[-1].date.year,
            normalize=normalize_chart,
            recession_periods=recession_periods,
        )
        answer_text = self.answer_service.write_single_series_lookup(analysis, normalize=normalize_chart)
        return QueryResponse(intent=response_intent, analysis=analysis, chart=chart, answer_text=answer_text)
