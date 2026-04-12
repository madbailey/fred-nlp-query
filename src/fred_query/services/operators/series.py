from __future__ import annotations

from datetime import date

from fred_query.schemas.analysis import DerivedMetric, HistoricalSeriesContext, ObservationPoint, SeriesAnalysis
from fred_query.schemas.chart import DateSpanAnnotation
from fred_query.schemas.intent import QueryIntent, TransformType
from fred_query.schemas.resolved_series import SeriesMetadata
from fred_query.services.fred_client import FREDClient
from fred_query.services.operators.models import (
    HistoricalSummaryResult,
    ResolvedSeriesResult,
    RelationshipMetricsResult,
    RelationshipSeriesTransformOutput,
    RelationshipTransformPlan,
    SingleSeriesTransformPlan,
    SingleSeriesTransformOutput,
)
from fred_query.services.resolver_service import ResolverService
from fred_query.services.transform_service import TransformService


class ResolveSeriesOp:
    def __init__(self, resolver_service: ResolverService) -> None:
        self.resolver_service = resolver_service

    def for_single_series(self, intent: QueryIntent) -> ResolvedSeriesResult:
        search_text = intent.search_text or " ".join(intent.indicators)
        resolved_series, metadata, search_match = self.resolver_service.resolve_series(
            explicit_series_id=intent.series_id,
            search_text=search_text,
            geography=intent.geographies[0].name if intent.geographies else "Unspecified",
            indicator=intent.indicators[0] if intent.indicators else "unknown_indicator",
        )
        return ResolvedSeriesResult(
            resolved_series=resolved_series,
            metadata=metadata,
            search_match=search_match,
        )

    @staticmethod
    def relationship_indicator_for_index(intent: QueryIntent, index: int, fallback: str) -> str:
        if index < len(intent.indicators) and intent.indicators[index]:
            return intent.indicators[index]
        return fallback

    @staticmethod
    def relationship_search_text_for_index(intent: QueryIntent, index: int) -> str | None:
        if index < len(intent.search_texts) and intent.search_texts[index]:
            return intent.search_texts[index]
        if len(intent.search_texts) == 1:
            return intent.search_texts[0]
        if index < len(intent.indicators) and intent.indicators[index]:
            return intent.indicators[index]
        return None

    @staticmethod
    def relationship_series_id_for_index(intent: QueryIntent, index: int) -> str | None:
        if index < len(intent.series_ids) and intent.series_ids[index]:
            return intent.series_ids[index]
        return None

    def for_relationship_target(self, intent: QueryIntent, index: int) -> ResolvedSeriesResult:
        search_text = self.relationship_search_text_for_index(intent, index)
        resolved_series, metadata, search_match = self.resolver_service.resolve_series(
            explicit_series_id=self.relationship_series_id_for_index(intent, index),
            search_text=search_text,
            geography="Unspecified",
            indicator=self.relationship_indicator_for_index(
                intent,
                index,
                search_text or "unknown_indicator",
            ),
            no_target_message="I need two resolvable series targets before I can run relationship analysis.",
        )
        return ResolvedSeriesResult(
            resolved_series=resolved_series,
            metadata=metadata,
            search_match=search_match,
        )


class FetchSeriesObservationsOp:
    def __init__(self, resolver_service: ResolverService) -> None:
        self.resolver_service = resolver_service

    def fetch(
        self,
        series_id: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        frequency: str | None = None,
        aggregation_method: str | None = None,
        limit: int | None = None,
        sort_order: str | None = None,
        empty_result_message: str | None = None,
    ) -> list[ObservationPoint]:
        return self.resolver_service.get_required_observations(
            series_id,
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            aggregation_method=aggregation_method,
            limit=limit,
            sort_order=sort_order,
            empty_result_message=empty_result_message,
        )


class ApplyTransformOp:
    def __init__(self, transform_service: TransformService) -> None:
        self.transform_service = transform_service

    def plan_single_series(
        self,
        intent: QueryIntent,
        *,
        metadata: SeriesMetadata,
        start_date: date,
        end_date: date | None,
    ) -> SingleSeriesTransformPlan:
        effective_transform = (
            TransformType.LEVEL if intent.transform == TransformType.NORMALIZED_INDEX else intent.transform
        )
        normalize_chart = intent.normalization or intent.transform == TransformType.NORMALIZED_INDEX
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
        return SingleSeriesTransformPlan(
            start_date=start_date,
            end_date=end_date,
            effective_transform=effective_transform,
            normalize_chart=normalize_chart,
            periods_per_year=periods_per_year,
            transform_window=transform_window,
            warmup_periods=warmup_periods,
            fetch_start_date=fetch_start_date,
            warnings=transform_warnings,
        )

    def apply_single_series(
        self,
        observations: list[ObservationPoint],
        *,
        metadata: SeriesMetadata,
        plan: SingleSeriesTransformPlan,
    ) -> SingleSeriesTransformOutput:
        visible_observations = self.transform_service.filter_observations_by_date(
            observations,
            start_date=plan.start_date,
            end_date=plan.end_date,
        )
        if not visible_observations:
            raise ValueError(f"No observations returned for {metadata.series_id} in the requested display window.")

        normalized_observations = None
        transformed_observations = None
        analysis_basis = None
        analysis_units = None
        total_growth = None
        compound_annual_growth_rate = None

        if plan.effective_transform == TransformType.LEVEL:
            normalized_observations = (
                self.transform_service.normalize_to_index(visible_observations) if plan.normalize_chart else None
            )
            latest_value, latest_date = self.transform_service.latest_value(visible_observations)
            total_growth = self.transform_service.calculate_total_growth_pct(visible_observations)
            compound_annual_growth_rate = self.transform_service.calculate_cagr_pct(visible_observations)
            comparison_units = metadata.units
            compare_on_transformed_series = False
        else:
            transform_result = self.transform_service.apply_single_series_transform(
                observations,
                transform=plan.effective_transform,
                units=metadata.units,
                frequency=metadata.frequency,
                window=plan.transform_window,
            )
            transformed_observations = self.transform_service.filter_observations_by_date(
                transform_result.observations or [],
                start_date=plan.start_date,
                end_date=plan.end_date,
            )
            if not transformed_observations:
                basis_label = transform_result.basis or plan.effective_transform.value.replace("_", " ")
                raise ValueError(f"I could not derive {basis_label} over the requested date range.")

            analysis_basis = transform_result.basis
            analysis_units = transform_result.units
            latest_value, latest_date = self.transform_service.latest_value(transformed_observations)
            comparison_units = analysis_units
            compare_on_transformed_series = transform_result.compare_on_transformed_series

        return SingleSeriesTransformOutput(
            visible_observations=visible_observations,
            transformed_observations=transformed_observations,
            normalized_observations=normalized_observations,
            analysis_basis=analysis_basis,
            analysis_units=analysis_units,
            latest_value=latest_value,
            latest_date=latest_date,
            comparison_units=comparison_units,
            compare_on_transformed_series=compare_on_transformed_series,
            total_growth_pct=total_growth,
            compound_annual_growth_rate_pct=compound_annual_growth_rate,
        )

    def plan_relationship(
        self,
        intent: QueryIntent,
        *,
        metadata_items: list[SeriesMetadata],
        start_date: date,
        end_date: date | None,
    ) -> RelationshipTransformPlan:
        frequency_code, frequency_label, periods_per_year, lag_unit = (
            self.transform_service.choose_relationship_frequency(
                [metadata.frequency for metadata in metadata_items]
            )
        )
        effective_transform = (
            TransformType.LEVEL if intent.transform == TransformType.NORMALIZED_INDEX else intent.transform
        )
        transform_window, transform_warnings = self.transform_service.resolve_transform_window(
            transform=effective_transform,
            frequency=metadata_items[0].frequency,
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
            frequency=frequency_code,
        )
        return RelationshipTransformPlan(
            start_date=start_date,
            end_date=end_date,
            frequency_code=frequency_code,
            frequency_label=frequency_label,
            periods_per_year=periods_per_year,
            lag_unit=lag_unit,
            requested_transform=intent.transform,
            effective_transform=effective_transform,
            normalization=intent.normalization,
            transform_window=transform_window,
            warmup_periods=warmup_periods,
            fetch_start_date=fetch_start_date,
            warnings=transform_warnings,
        )

    def apply_relationship_basis(
        self,
        observations: list[ObservationPoint],
        *,
        metadata: SeriesMetadata,
        plan: RelationshipTransformPlan,
    ) -> RelationshipSeriesTransformOutput:
        visible_observations = self.transform_service.filter_observations_by_date(
            observations,
            start_date=plan.start_date,
            end_date=plan.end_date,
        )
        if not visible_observations:
            raise ValueError(f"No observations returned for {metadata.series_id} in the requested display window.")

        basis_source_observations = observations if plan.warmup_periods > 0 else visible_observations
        transformed, basis, units, applied_window, basis_warnings = self.transform_service.build_relationship_basis(
            basis_source_observations,
            title=metadata.title,
            units=metadata.units,
            frequency=metadata.frequency,
            periods_per_year=plan.periods_per_year,
            transform=plan.requested_transform,
            normalization=plan.normalization,
            requested_window=plan.transform_window,
        )
        if not transformed:
            raise ValueError(
                f"I could not derive a stable comparison basis for {metadata.series_id} over the requested date range."
            )

        transformed = self.transform_service.filter_observations_by_date(
            transformed,
            start_date=plan.start_date,
            end_date=plan.end_date,
        )
        if not transformed:
            raise ValueError(
                f"I could not derive {basis.lower()} for {metadata.series_id} over the requested display window."
            )

        return RelationshipSeriesTransformOutput(
            visible_observations=visible_observations,
            transformed_observations=transformed,
            basis=basis,
            units=units,
            applied_transform_window=applied_window,
            warnings=basis_warnings,
        )


class AlignSeriesOp:
    def __init__(self, transform_service: TransformService) -> None:
        self.transform_service = transform_service

    def align(
        self,
        first: list[ObservationPoint],
        second: list[ObservationPoint],
    ) -> tuple[list[ObservationPoint], list[ObservationPoint]]:
        return self.transform_service.align_on_dates(first, second)

    def standardize(self, observations: list[ObservationPoint]) -> list[ObservationPoint]:
        return self.transform_service.standardize(observations)


class ComputeRelationshipMetricsOp:
    def __init__(self, transform_service: TransformService) -> None:
        self.transform_service = transform_service

    def compute(
        self,
        first: list[ObservationPoint],
        second: list[ObservationPoint],
        *,
        periods_per_year: int,
    ) -> RelationshipMetricsResult:
        same_period_correlation = self.transform_service.calculate_correlation(first, second)
        regression_slope = self.transform_service.calculate_regression_slope(first, second)
        best_lag, best_lag_correlation, best_lag_samples = self.transform_service.calculate_best_lag_correlation(
            first,
            second,
            max_lag=self.transform_service.relationship_max_lag(periods_per_year),
        )
        return RelationshipMetricsResult(
            same_period_correlation=same_period_correlation,
            regression_slope=regression_slope,
            best_lag=best_lag,
            best_lag_correlation=best_lag_correlation,
            best_lag_samples=best_lag_samples,
        )


class ComputeSeriesMetricsOp:
    _HISTORICAL_LOOKBACK_YEARS = 50

    def __init__(
        self,
        *,
        transform_service: TransformService,
        fetch_observations_op: FetchSeriesObservationsOp,
    ) -> None:
        self.transform_service = transform_service
        self.fetch_observations_op = fetch_observations_op

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

    def summarize_historical_context(
        self,
        *,
        series_id: str,
        metadata: SeriesMetadata,
        observations: list[ObservationPoint],
        transform_plan: SingleSeriesTransformPlan,
        transform_result: SingleSeriesTransformOutput,
    ) -> HistoricalSummaryResult:
        if transform_result.latest_date is None:
            historical_series = self.transform_service.filter_observations_by_date(
                observations,
                start_date=transform_plan.start_date,
                end_date=None,
            )
            context = self.transform_service.summarize_historical_context(historical_series)
            return HistoricalSummaryResult(
                context=context,
                metrics=self._historical_metrics(units=transform_result.comparison_units, context=context),
            )

        historical_start = self._historical_start_date(
            start_date=transform_plan.start_date,
            latest_date=transform_result.latest_date,
        )
        historical_fetch_start = historical_start
        warnings: list[str] = []
        if transform_result.compare_on_transformed_series:
            historical_fetch_start = self.transform_service.subtract_periods(
                historical_start,
                periods=transform_plan.warmup_periods,
                frequency=metadata.frequency,
            )

        try:
            historical_observations = self.fetch_observations_op.fetch(
                series_id,
                start_date=historical_fetch_start,
                end_date=transform_result.latest_date,
            )
        except Exception:
            historical_observations = observations
            if observations and historical_fetch_start < observations[0].date:
                warnings.append(
                    "Extended historical context was unavailable, so comparisons use only the requested range."
                )

        historical_series = self.transform_service.filter_observations_by_date(
            historical_observations,
            start_date=historical_start,
            end_date=transform_result.latest_date,
        )
        if transform_result.compare_on_transformed_series:
            transformed_history = self.transform_service.apply_single_series_transform(
                historical_observations,
                transform=transform_plan.effective_transform,
                units=metadata.units,
                frequency=metadata.frequency,
                window=transform_plan.transform_window,
            )
            history_basis = self.transform_service.filter_observations_by_date(
                transformed_history.observations or [],
                start_date=historical_start,
                end_date=transform_result.latest_date,
            )
            if history_basis:
                historical_series = history_basis
            else:
                warnings.append(
                    "Historical transform context could not be derived cleanly, so context uses only the requested display window."
                )
                historical_series = (
                    transform_result.transformed_observations
                    or transform_result.visible_observations
                )

        context = self.transform_service.summarize_historical_context(historical_series)
        return HistoricalSummaryResult(
            context=context,
            metrics=self._historical_metrics(units=transform_result.comparison_units, context=context),
            warnings=warnings,
        )


class RankSeriesOp:
    @staticmethod
    def rank(
        series_results: list[SeriesAnalysis],
        *,
        descending: bool,
    ) -> list[SeriesAnalysis]:
        return sorted(
            series_results,
            key=lambda result: result.latest_value if result.latest_value is not None else float("-inf"),
            reverse=descending,
        )


class FetchRecessionPeriodsOp:
    def __init__(self, *, fred_client: FREDClient, transform_service: TransformService) -> None:
        self.fred_client = fred_client
        self.transform_service = transform_service

    def fetch(self, *, start_date: date, end_date: date) -> list[DateSpanAnnotation]:
        try:
            recession_observations = self.fred_client.get_series_observations(
                "USREC",
                start_date=start_date,
                end_date=end_date,
            )
            return self.transform_service.derive_recession_periods(recession_observations)
        except Exception:
            return []
