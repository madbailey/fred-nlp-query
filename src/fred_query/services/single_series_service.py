from __future__ import annotations

from datetime import date, timedelta

from fred_query.schemas.analysis import (
    AnalysisResult,
    DerivedMetric,
    QueryIntent,
    QueryResponse,
    SeriesAnalysis,
)
from fred_query.services.answer_service import AnswerService
from fred_query.services.chart_service import ChartService
from fred_query.services.fred_client import FREDClient
from fred_query.services.operators import (
    ApplyTransformOp,
    BuildChartOp,
    ComputeSeriesMetricsOp,
    FetchRecessionPeriodsOp,
    FetchSeriesObservationsOp,
    RenderAnswerOp,
    ResolveSeriesOp,
)
from fred_query.services.resolver_service import ResolverService
from fred_query.schemas.intent import TransformType
from fred_query.services.transform_service import TransformService
from fred_query.services.vintage_analysis_service import VintageAnalysisService


class SingleSeriesLookupService:
    """Deterministic single-series lookup based on a FRED series ID or search phrase."""

    def __init__(
        self,
        fred_client: FREDClient,
        *,
        resolver_service: ResolverService | None = None,
        transform_service: TransformService | None = None,
        chart_service: ChartService | None = None,
        answer_service: AnswerService | None = None,
        vintage_analysis_service: VintageAnalysisService | None = None,
        resolve_series_op: ResolveSeriesOp | None = None,
        fetch_observations_op: FetchSeriesObservationsOp | None = None,
        apply_transform_op: ApplyTransformOp | None = None,
        compute_metrics_op: ComputeSeriesMetricsOp | None = None,
        fetch_recession_periods_op: FetchRecessionPeriodsOp | None = None,
        build_chart_op: BuildChartOp | None = None,
        render_answer_op: RenderAnswerOp | None = None,
    ) -> None:
        self.fred_client = fred_client
        self.resolver_service = resolver_service or ResolverService(fred_client)
        self.transform_service = transform_service or TransformService()
        self.transform_planning_service = self.transform_service.planning_service
        self.series_transform_service = self.transform_service.series_transform_service
        self.series_statistics_service = self.transform_service.series_statistics_service
        self.chart_service = chart_service or ChartService()
        self.answer_service = answer_service or AnswerService()
        self.vintage_analysis_service = vintage_analysis_service or VintageAnalysisService(fred_client)
        self.resolve_series_op = resolve_series_op or ResolveSeriesOp(self.resolver_service)
        self.fetch_observations_op = fetch_observations_op or FetchSeriesObservationsOp(self.resolver_service)
        self.apply_transform_op = apply_transform_op or ApplyTransformOp(self.transform_service)
        self.compute_metrics_op = compute_metrics_op or ComputeSeriesMetricsOp(
            transform_service=self.transform_service,
            fetch_observations_op=self.fetch_observations_op,
        )
        self.fetch_recession_periods_op = fetch_recession_periods_op or FetchRecessionPeriodsOp(
            fred_client=fred_client,
            transform_service=self.transform_service,
        )
        self.build_chart_op = build_chart_op or BuildChartOp(self.chart_service)
        self.render_answer_op = render_answer_op or RenderAnswerOp(self.answer_service)

    @staticmethod
    def _default_start_date() -> date:
        return date.today() - timedelta(days=365 * 10)

    def lookup(self, intent: QueryIntent) -> QueryResponse:
        response_intent = intent.model_copy(deep=True)
        start_date = intent.start_date or self._default_start_date()
        end_date = intent.end_date

        resolved = self.resolve_series_op.for_single_series(intent)
        resolved_series = resolved.resolved_series
        metadata = resolved.metadata
        search_match = resolved.search_match
        response_intent.series_id = metadata.series_id
        if not response_intent.search_text:
            response_intent.search_text = search_match.title if search_match is not None else metadata.title
        if not response_intent.indicators:
            response_intent.indicators = [resolved_series.indicator]

        transform_plan = self.apply_transform_op.plan_single_series(
            intent,
            metadata=metadata,
            start_date=start_date,
            end_date=end_date,
        )
        observations = self.fetch_observations_op.fetch(
            metadata.series_id,
            start_date=transform_plan.fetch_start_date,
            end_date=end_date,
        )

        warnings = list(transform_plan.warnings)
        transform_result = self.apply_transform_op.apply_single_series(
            observations,
            metadata=metadata,
            plan=transform_plan,
        )
        historical_summary = self.compute_metrics_op.summarize_historical_context(
            series_id=metadata.series_id,
            metadata=metadata,
            observations=observations,
            transform_plan=transform_plan,
            transform_result=transform_result,
        )
        warnings.extend(historical_summary.warnings)

        recession_periods = self.fetch_recession_periods_op.fetch(
            start_date=transform_result.visible_observations[0].date,
            end_date=transform_result.visible_observations[-1].date,
        )

        series_analysis = SeriesAnalysis(
            series=resolved_series,
            observations=transform_result.visible_observations,
            transformed_observations=(
                transform_result.transformed_observations or transform_result.normalized_observations
            ),
            historical_context=historical_summary.context,
            analysis_basis=transform_result.analysis_basis,
            analysis_units=transform_result.analysis_units,
            total_growth_pct=transform_result.total_growth_pct,
            compound_annual_growth_rate_pct=transform_result.compound_annual_growth_rate_pct,
            latest_value=transform_result.latest_value,
            latest_observation_date=transform_result.latest_date,
        )
        derived_metrics = [
            DerivedMetric(
                name="top_search_match",
                value=search_match.series_id if search_match is not None else metadata.series_id,
                description="The series selected for execution.",
            )
        ]
        if transform_result.analysis_basis:
            derived_metrics.append(
                DerivedMetric(
                    name="analysis_basis",
                    value=transform_result.analysis_basis,
                    description="Transformation applied before charting and historical comparison.",
                )
            )
        if transform_plan.transform_window is not None and transform_plan.effective_transform in (
            TransformType.ROLLING_AVERAGE,
            TransformType.ROLLING_STDDEV,
            TransformType.ROLLING_VOLATILITY,
        ):
            derived_metrics.append(
                DerivedMetric(
                    name="applied_transform_window",
                    value=transform_plan.transform_window,
                    unit="observations",
                    description="Rolling window length used for the displayed transform.",
                )
            )
        display_observations = (
            transform_result.transformed_observations
            or transform_result.visible_observations
            or transform_result.normalized_observations
        )
        analysis = AnalysisResult(
            series_results=[series_analysis],
            derived_metrics=derived_metrics + historical_summary.metrics,
            warnings=warnings,
            latest_observation_date=transform_result.latest_date,
            coverage_start=display_observations[0].date,
            coverage_end=display_observations[-1].date,
        )

        # Add vintage analysis if requested
        if intent.needs_revision_analysis:
            try:
                vintage_analysis = self.vintage_analysis_service.analyze_vintage_data(resolved_series)

                # Add vintage-specific derived metrics
                for comparison in vintage_analysis.comparisons[:3]:  # Limit to first 3 comparisons
                    if comparison.first_release_value is not None and comparison.current_value is not None:
                        percent_change = comparison.percent_change_from_first
                        if percent_change is not None:
                            analysis.derived_metrics.append(
                                DerivedMetric(
                                    name=f"vintage_revision_{comparison.observation_date.isoformat()}",
                                    value=round(percent_change, 4),
                                    unit="%",
                                    description=(
                                        f"Revision impact for {comparison.observation_date.isoformat()}: "
                                        f"first release {comparison.first_release_value:.4f} vs "
                                        f"current {comparison.current_value:.4f} ({percent_change:+.2f}%)"
                                    ),
                                )
                            )

                # Add summary vintage metric if available
                if vintage_analysis.summary_stats:
                    avg_change = vintage_analysis.summary_stats.get("average_revision_impact_pct")
                    if avg_change is not None:
                        analysis.derived_metrics.append(
                            DerivedMetric(
                                name="average_vintage_revision_impact",
                                value=round(avg_change, 4),
                                unit="%",
                                description="Average percentage change from first release across all vintage revisions",
                            )
                        )
            except Exception as e:
                # If vintage analysis fails, add a warning but continue
                analysis.warnings.append(f"Vintage analysis unavailable: {str(e)}")

        chart = self.build_chart_op.build_single_series_chart(
            series_result=series_analysis,
            start_year=(
                analysis.coverage_start.year
                if analysis.coverage_start
                else transform_result.visible_observations[0].date.year
            ),
            end_year=(
                analysis.coverage_end.year
                if analysis.coverage_end
                else transform_result.visible_observations[-1].date.year
            ),
            normalize=transform_plan.normalize_chart,
            recession_periods=recession_periods,
        )
        answer_text = self.render_answer_op.render_single_series_answer(
            analysis,
            normalize=transform_plan.normalize_chart,
        )
        return QueryResponse(intent=response_intent, analysis=analysis, chart=chart, answer_text=answer_text)
