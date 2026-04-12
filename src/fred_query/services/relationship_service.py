from __future__ import annotations

from datetime import date, timedelta

from fred_query.schemas.analysis import (
    AnalysisResult,
    DerivedMetric,
    QueryResponse,
    RelationshipSummary,
    SeriesAnalysis,
)
from fred_query.services.answer_service import AnswerService
from fred_query.services.chart_service import ChartService
from fred_query.services.fred_client import FREDClient
from fred_query.services.operators import (
    AlignSeriesOp,
    ApplyTransformOp,
    BuildChartOp,
    ComputeRelationshipMetricsOp,
    FetchSeriesObservationsOp,
    RenderAnswerOp,
    ResolveSeriesOp,
)
from fred_query.services.resolver_service import ResolverService
from fred_query.services.transform_service import TransformService
from fred_query.schemas.intent import QueryIntent, TransformType


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
        resolve_series_op: ResolveSeriesOp | None = None,
        fetch_observations_op: FetchSeriesObservationsOp | None = None,
        apply_transform_op: ApplyTransformOp | None = None,
        align_series_op: AlignSeriesOp | None = None,
        compute_relationship_metrics_op: ComputeRelationshipMetricsOp | None = None,
        build_chart_op: BuildChartOp | None = None,
        render_answer_op: RenderAnswerOp | None = None,
    ) -> None:
        self.fred_client = fred_client
        self.resolver_service = resolver_service or ResolverService(fred_client)
        self.transform_service = transform_service or TransformService()
        self.chart_service = chart_service or ChartService()
        self.answer_service = answer_service or AnswerService()
        self.resolve_series_op = resolve_series_op or ResolveSeriesOp(self.resolver_service)
        self.fetch_observations_op = fetch_observations_op or FetchSeriesObservationsOp(self.resolver_service)
        self.apply_transform_op = apply_transform_op or ApplyTransformOp(self.transform_service)
        self.align_series_op = align_series_op or AlignSeriesOp(self.transform_service)
        self.compute_relationship_metrics_op = compute_relationship_metrics_op or ComputeRelationshipMetricsOp(
            self.transform_service
        )
        self.build_chart_op = build_chart_op or BuildChartOp(self.chart_service)
        self.render_answer_op = render_answer_op or RenderAnswerOp(self.answer_service)

    @staticmethod
    def _default_start_date() -> date:
        return date.today() - timedelta(days=365 * 10)

    @staticmethod
    def _lag_description(first_name: str, second_name: str, lag: int, lag_unit: str) -> str:
        if lag == 0:
            return "The strongest absolute correlation in the tested lag window occurs in the same period."
        if lag > 0:
            return f"Positive values mean {first_name} tends to lead {second_name} by {lag} {lag_unit}."
        return f"Negative values mean {second_name} tends to lead {first_name} by {abs(lag)} {lag_unit}."

    def analyze(self, intent: QueryIntent) -> QueryResponse:
        response_intent = intent.model_copy(deep=True)
        resolved_series = []
        metadata_items = []
        for index in range(2):
            target = self.resolve_series_op.for_relationship_target(intent, index)
            resolved_series.append(target.resolved_series)
            metadata_items.append(target.metadata)
        response_intent.series_ids = [metadata.series_id for metadata in metadata_items]
        response_intent.search_texts = [
            self.resolve_series_op.relationship_search_text_for_index(intent, index) or metadata.title
            for index, metadata in enumerate(metadata_items)
        ]
        if not response_intent.indicators:
            response_intent.indicators = [
                self.resolve_series_op.relationship_indicator_for_index(intent, index, metadata.title)
                for index, metadata in enumerate(metadata_items)
            ]

        start_date = intent.start_date or self._default_start_date()
        end_date = intent.end_date
        transform_plan = self.apply_transform_op.plan_relationship(
            intent,
            metadata_items=metadata_items,
            start_date=start_date,
            end_date=end_date,
        )
        raw_observations = []
        transformed_observations = []
        bases: list[str] = []
        analysis_units: list[str] = []
        warnings = list(transform_plan.warnings)
        applied_transform_window: int | None = None

        for metadata in metadata_items:
            observations = self.fetch_observations_op.fetch(
                metadata.series_id,
                start_date=transform_plan.fetch_start_date,
                end_date=end_date,
                frequency=transform_plan.frequency_code,
                aggregation_method="avg",
            )
            transformed = self.apply_transform_op.apply_relationship_basis(
                observations,
                metadata=metadata,
                plan=transform_plan,
            )

            raw_observations.append(transformed.visible_observations)
            transformed_observations.append(transformed.transformed_observations)
            bases.append(transformed.basis)
            analysis_units.append(transformed.units)
            if transformed.applied_transform_window is not None:
                applied_transform_window = transformed.applied_transform_window
            warnings.extend(transformed.warnings)

        aligned_first, aligned_second = self.align_series_op.align(
            transformed_observations[0],
            transformed_observations[1],
        )
        if len(aligned_first) < 8:
            raise ValueError(
                "The two series do not have enough overlapping observations after alignment to estimate a relationship safely."
            )

        relationship_metrics = self.compute_relationship_metrics_op.compute(
            aligned_first,
            aligned_second,
            periods_per_year=transform_plan.periods_per_year,
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
                self.align_series_op.standardize(aligned_first),
                self.align_series_op.standardize(aligned_second),
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
                value=transform_plan.frequency_label,
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
        if applied_transform_window is not None and transform_plan.effective_transform in (
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

        if relationship_metrics.same_period_correlation is not None:
            derived_metrics.append(
                DerivedMetric(
                    name="same_period_correlation",
                    label="Same-period correlation",
                    value=round(relationship_metrics.same_period_correlation, 4),
                    description="Pearson correlation on the aligned analysis basis in the same period.",
                )
            )

        if relationship_metrics.regression_slope is not None:
            derived_metrics.append(
                DerivedMetric(
                    name="regression_slope",
                    label="Regression slope",
                    value=round(relationship_metrics.regression_slope, 4),
                    description=(
                        f"Simple linear slope of {resolved_series[1].series_id} on {resolved_series[0].series_id} "
                        "using the aligned analysis basis."
                    ),
                )
            )

        if relationship_metrics.best_lag is not None and relationship_metrics.best_lag_correlation is not None:
            derived_metrics.extend(
                [
                    DerivedMetric(
                        name="strongest_lag_periods",
                        label="Strongest lag",
                        value=relationship_metrics.best_lag,
                        unit=transform_plan.lag_unit,
                        description=self._lag_description(
                            resolved_series[0].series_id,
                            resolved_series[1].series_id,
                            relationship_metrics.best_lag,
                            transform_plan.lag_unit,
                        ),
                    ),
                    DerivedMetric(
                        name="strongest_lag_correlation",
                        label="Strongest lag correlation",
                        value=round(relationship_metrics.best_lag_correlation, 4),
                        description=(
                            "Absolute strongest correlation in the tested lead-lag window using "
                            f"{relationship_metrics.best_lag_samples} overlapping observations."
                        ),
                    ),
                ]
            )

        analysis = AnalysisResult(
            series_results=series_results,
            derived_metrics=derived_metrics,
            relationship_summary=RelationshipSummary(
                analysis_basis=basis_summary,
                common_frequency=transform_plan.frequency_label,
                overlap_observations=len(aligned_first),
                same_period_correlation=round(relationship_metrics.same_period_correlation, 4)
                if relationship_metrics.same_period_correlation is not None
                else None,
                regression_slope=(
                    round(relationship_metrics.regression_slope, 4)
                    if relationship_metrics.regression_slope is not None
                    else None
                ),
                strongest_lag_periods=relationship_metrics.best_lag,
                strongest_lag_unit=transform_plan.lag_unit if relationship_metrics.best_lag is not None else None,
                strongest_lag_correlation=round(relationship_metrics.best_lag_correlation, 4)
                if relationship_metrics.best_lag_correlation is not None
                else None,
                strongest_lag_observations=relationship_metrics.best_lag_samples,
            ),
            warnings=warnings,
            latest_observation_date=max(latest_dates),
            coverage_start=aligned_first[0].date,
            coverage_end=aligned_first[-1].date,
        )
        chart = self.build_chart_op.build_relationship_chart(
            series_results=series_results,
            frequency_label=transform_plan.frequency_label,
            chart_basis=chart_basis,
            chart_units=chart_units,
            start_date=aligned_first[0].date,
            end_date=aligned_first[-1].date,
        )
        answer_text = self.render_answer_op.render_relationship_answer(analysis)
        response_intent.refresh_query_plan()
        return QueryResponse(intent=response_intent, analysis=analysis, chart=chart, answer_text=answer_text)
