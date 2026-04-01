from __future__ import annotations

from datetime import date, timedelta

from fred_query.schemas.analysis import (
    AnalysisResult,
    DerivedMetric,
    QueryIntent,
    QueryResponse,
    RelationshipSummary,
    SeriesAnalysis,
)
from fred_query.schemas.resolved_series import ResolvedSeries, SeriesMetadata
from fred_query.services.answer_service import AnswerService
from fred_query.services.chart_service import ChartService
from fred_query.services.fred_client import FREDClient
from fred_query.services.resolver_service import ResolverService
from fred_query.services.transform_service import TransformService
from fred_query.schemas.intent import TransformType


class RelationshipAnalysisService:
    """Deterministic pairwise analysis for non-state FRED relationship questions."""

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
        self.transform_planning_service = self.transform_service.planning_service
        self.series_transform_service = self.transform_service.series_transform_service
        self.relationship_transform_service = self.transform_service.relationship_transform_service
        self.chart_service = chart_service or ChartService()
        self.answer_service = answer_service or AnswerService()

    @staticmethod
    def _default_start_date() -> date:
        return date.today() - timedelta(days=365 * 10)

    @staticmethod
    def _indicator_for_index(intent: QueryIntent, index: int, fallback: str) -> str:
        if index < len(intent.indicators) and intent.indicators[index]:
            return intent.indicators[index]
        return fallback

    @staticmethod
    def _search_text_for_index(intent: QueryIntent, index: int) -> str | None:
        if index < len(intent.search_texts) and intent.search_texts[index]:
            return intent.search_texts[index]
        if len(intent.search_texts) == 1:
            return intent.search_texts[0]
        if index < len(intent.indicators) and intent.indicators[index]:
            return intent.indicators[index]
        return None

    @staticmethod
    def _series_id_for_index(intent: QueryIntent, index: int) -> str | None:
        if index < len(intent.series_ids) and intent.series_ids[index]:
            return intent.series_ids[index]
        return None

    @staticmethod
    def _lag_description(first_name: str, second_name: str, lag: int, lag_unit: str) -> str:
        if lag == 0:
            return "The strongest absolute correlation in the tested lag window occurs in the same period."
        if lag > 0:
            return f"Positive values mean {first_name} tends to lead {second_name} by {lag} {lag_unit}."
        return f"Negative values mean {second_name} tends to lead {first_name} by {abs(lag)} {lag_unit}."

    def _resolve_series(self, intent: QueryIntent, index: int) -> tuple[ResolvedSeries, SeriesMetadata]:
        resolved, metadata, _ = self.resolver_service.resolve_series(
            explicit_series_id=self._series_id_for_index(intent, index),
            search_text=self._search_text_for_index(intent, index),
            geography="Unspecified",
            indicator=self._indicator_for_index(
                intent,
                index,
                self._search_text_for_index(intent, index) or "unknown_indicator",
            ),
            no_target_message="I need two resolvable series targets before I can run relationship analysis.",
        )
        return resolved, metadata

    def analyze(self, intent: QueryIntent) -> QueryResponse:
        response_intent = intent.model_copy(deep=True)
        resolved_series: list[ResolvedSeries] = []
        metadata_items: list[SeriesMetadata] = []
        for index in range(2):
            resolved, metadata = self._resolve_series(intent, index)
            resolved_series.append(resolved)
            metadata_items.append(metadata)
        response_intent.series_ids = [metadata.series_id for metadata in metadata_items]
        response_intent.search_texts = [
            self._search_text_for_index(intent, index) or metadata.title
            for index, metadata in enumerate(metadata_items)
        ]
        if not response_intent.indicators:
            response_intent.indicators = [
                self._indicator_for_index(intent, index, metadata.title)
                for index, metadata in enumerate(metadata_items)
            ]

        frequency_code, frequency_label, periods_per_year, lag_unit = (
            self.relationship_transform_service.choose_relationship_frequency(
                [metadata.frequency for metadata in metadata_items]
            )
        )

        start_date = intent.start_date or self._default_start_date()
        end_date = intent.end_date
        effective_transform = (
            TransformType.LEVEL if intent.transform == TransformType.NORMALIZED_INDEX else intent.transform
        )
        transform_window, transform_warnings = self.transform_planning_service.resolve_transform_window(
            transform=effective_transform,
            frequency=metadata_items[0].frequency,
            requested_window=intent.transform_window,
        )
        warmup_periods = self.transform_planning_service.transform_warmup_periods(
            transform=effective_transform,
            periods_per_year=periods_per_year,
            window=transform_window,
        )
        fetch_start_date = self.transform_planning_service.subtract_periods(
            start_date,
            periods=warmup_periods,
            frequency=frequency_code,
        )
        raw_observations: list[list] = []
        transformed_observations: list[list] = []
        bases: list[str] = []
        analysis_units: list[str] = []
        warnings = list(transform_warnings)
        applied_transform_window: int | None = None

        for metadata in metadata_items:
            observations = self.resolver_service.get_required_observations(
                metadata.series_id,
                start_date=fetch_start_date,
                end_date=end_date,
                frequency=frequency_code,
                aggregation_method="avg",
            )

            visible_observations = self.series_transform_service.filter_observations_by_date(
                observations,
                start_date=start_date,
                end_date=end_date,
            )
            if not visible_observations:
                raise ValueError(f"No observations returned for {metadata.series_id} in the requested display window.")

            basis_source_observations = observations if warmup_periods > 0 else visible_observations
            transformed, basis, units, applied_window, basis_warnings = (
                self.relationship_transform_service.build_relationship_basis(
                    basis_source_observations,
                    title=metadata.title,
                    units=metadata.units,
                    frequency=metadata.frequency,
                    periods_per_year=periods_per_year,
                    transform=intent.transform,
                    normalization=intent.normalization,
                    requested_window=transform_window,
                )
            )
            if not transformed:
                raise ValueError(
                    f"I could not derive a stable comparison basis for {metadata.series_id} over the requested date range."
                )

            transformed = self.series_transform_service.filter_observations_by_date(
                transformed,
                start_date=start_date,
                end_date=end_date,
            )
            if not transformed:
                raise ValueError(
                    f"I could not derive {basis.lower()} for {metadata.series_id} over the requested display window."
                )

            raw_observations.append(visible_observations)
            transformed_observations.append(transformed)
            bases.append(basis)
            analysis_units.append(units)
            if applied_window is not None:
                applied_transform_window = applied_window
            warnings.extend(basis_warnings)

        aligned_first, aligned_second = self.relationship_transform_service.align_on_dates(
            transformed_observations[0],
            transformed_observations[1],
        )
        if len(aligned_first) < 8:
            raise ValueError(
                "The two series do not have enough overlapping observations after alignment to estimate a relationship safely."
            )

        same_period_correlation = self.relationship_transform_service.calculate_correlation(
            aligned_first,
            aligned_second,
        )
        regression_slope = self.relationship_transform_service.calculate_regression_slope(
            aligned_first,
            aligned_second,
        )
        best_lag, best_lag_correlation, best_lag_samples = (
            self.relationship_transform_service.calculate_best_lag_correlation(
                aligned_first,
                aligned_second,
                max_lag=self.relationship_transform_service.relationship_max_lag(periods_per_year),
            )
        )

        chart_series = [aligned_first, aligned_second]
        chart_units = analysis_units[0]
        basis_summary = (
            bases[0]
            if bases[0] == bases[1]
            else f"{resolved_series[0].series_id}: {bases[0]}; {resolved_series[1].series_id}: {bases[1]}"
        )
        chart_basis = basis_summary
        if analysis_units[0] != analysis_units[1]:
            chart_series = [
                self.relationship_transform_service.standardize(aligned_first),
                self.relationship_transform_service.standardize(aligned_second),
            ]
            chart_units = "Standard deviations"
            chart_basis = "Standardized relationship basis"
            warnings.append(
                "Chart values were standardized because the analysis basis produced different units across the two series."
            )

        latest_dates = [series[-1].date for series in raw_observations]
        latest_values = [series[-1].value for series in raw_observations]
        series_results = [
            SeriesAnalysis(
                series=resolved_series[index],
                observations=raw_observations[index],
                transformed_observations=chart_series[index],
                analysis_basis=bases[index],
                analysis_units=analysis_units[index],
                latest_value=latest_values[index],
                latest_observation_date=latest_dates[index],
            )
            for index in range(2)
        ]

        derived_metrics = [
            DerivedMetric(
                name="analysis_basis",
                label="Analysis basis",
                value=basis_summary,
                description="Transformation used to make the pairwise comparison more stable and interpretable.",
            ),
            DerivedMetric(
                name="common_frequency",
                label="Common frequency",
                value=frequency_label,
                description="Frequency used to align the two series before estimating the relationship.",
            ),
            DerivedMetric(
                name="overlap_observations",
                label="Overlap observations",
                value=len(aligned_first),
                unit="observations",
                description="Number of aligned observations used in the same-period relationship estimate.",
            ),
        ]
        if applied_transform_window is not None and effective_transform in (
            TransformType.ROLLING_AVERAGE,
            TransformType.ROLLING_STDDEV,
            TransformType.ROLLING_VOLATILITY,
        ):
            derived_metrics.append(
                DerivedMetric(
                    name="applied_transform_window",
                    value=applied_transform_window,
                    unit="observations",
                    description="Rolling window length used for the pairwise analysis basis.",
                )
            )

        if same_period_correlation is not None:
            derived_metrics.append(
                DerivedMetric(
                    name="same_period_correlation",
                    label="Same-period correlation",
                    value=round(same_period_correlation, 4),
                    description="Pearson correlation on the aligned analysis basis in the same period.",
                )
            )

        if regression_slope is not None:
            derived_metrics.append(
                DerivedMetric(
                    name="regression_slope",
                    label="Regression slope",
                    value=round(regression_slope, 4),
                    description=(
                        f"Simple linear slope of {resolved_series[1].series_id} on {resolved_series[0].series_id} "
                        "using the aligned analysis basis."
                    ),
                )
            )

        if best_lag is not None and best_lag_correlation is not None:
            derived_metrics.extend(
                [
                    DerivedMetric(
                        name="strongest_lag_periods",
                        label="Strongest lag",
                        value=best_lag,
                        unit=lag_unit,
                        description=self._lag_description(
                            resolved_series[0].series_id,
                            resolved_series[1].series_id,
                            best_lag,
                            lag_unit,
                        ),
                    ),
                    DerivedMetric(
                        name="strongest_lag_correlation",
                        label="Strongest lag correlation",
                        value=round(best_lag_correlation, 4),
                        description=(
                            f"Absolute strongest correlation in the tested lead-lag window using {best_lag_samples} "
                            "overlapping observations."
                        ),
                    ),
                ]
            )

        analysis = AnalysisResult(
            series_results=series_results,
            derived_metrics=derived_metrics,
            relationship_summary=RelationshipSummary(
                analysis_basis=basis_summary,
                common_frequency=frequency_label,
                overlap_observations=len(aligned_first),
                same_period_correlation=round(same_period_correlation, 4)
                if same_period_correlation is not None
                else None,
                regression_slope=round(regression_slope, 4) if regression_slope is not None else None,
                strongest_lag_periods=best_lag,
                strongest_lag_unit=lag_unit if best_lag is not None else None,
                strongest_lag_correlation=round(best_lag_correlation, 4)
                if best_lag_correlation is not None
                else None,
                strongest_lag_observations=best_lag_samples,
            ),
            warnings=warnings,
            latest_observation_date=max(latest_dates),
            coverage_start=aligned_first[0].date,
            coverage_end=aligned_first[-1].date,
        )
        chart = self.chart_service.build_relationship_chart(
            series_results=series_results,
            frequency_label=frequency_label,
            chart_basis=chart_basis,
            chart_units=chart_units,
            start_date=aligned_first[0].date,
            end_date=aligned_first[-1].date,
        )
        answer_text = self.answer_service.write_relationship_analysis(analysis)
        return QueryResponse(intent=response_intent, analysis=analysis, chart=chart, answer_text=answer_text)
