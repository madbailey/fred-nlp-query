from __future__ import annotations

from datetime import date

from fred_query.schemas.analysis import AnalysisResult, DerivedMetric, QueryResponse, SeriesAnalysis
from fred_query.services.answer_service import AnswerService
from fred_query.services.chart_service import ChartService
from fred_query.services.fred_client import FREDClient
from fred_query.services.intent_service import IntentService
from fred_query.services.resolver_service import ResolverService
from fred_query.services.transform_service import TransformService


class StateGDPComparisonService:
    """End-to-end deterministic workflow for the first comparison use case."""

    def __init__(
        self,
        fred_client: FREDClient,
        *,
        intent_service: IntentService | None = None,
        resolver_service: ResolverService | None = None,
        transform_service: TransformService | None = None,
        chart_service: ChartService | None = None,
        answer_service: AnswerService | None = None,
    ) -> None:
        self.fred_client = fred_client
        self.intent_service = intent_service or IntentService()
        self.resolver_service = resolver_service or ResolverService(fred_client)
        self.transform_service = transform_service or TransformService()
        self.series_transform_service = self.transform_service.series_transform_service
        self.series_statistics_service = self.transform_service.series_statistics_service
        self.chart_service = chart_service or ChartService()
        self.answer_service = answer_service or AnswerService()

    def compare(
        self,
        *,
        state1: str,
        state2: str,
        start_date: date,
        end_date: date | None = None,
        normalize: bool = True,
    ) -> QueryResponse:
        intent = self.intent_service.build_state_gdp_comparison_intent(
            state1=state1,
            state2=state2,
            start_date=start_date,
            end_date=end_date,
            normalize=normalize,
        )

        resolved_series = [
            self.resolver_service.resolve_state_gdp_series(state1),
            self.resolver_service.resolve_state_gdp_series(state2),
        ]

        series_results: list[SeriesAnalysis] = []
        warnings: list[str] = []
        coverage_start: date | None = None
        coverage_end: date | None = None
        latest_observation_date: date | None = None

        for series in resolved_series:
            observations = self.fred_client.get_series_observations(
                series.series_id,
                start_date=start_date,
                end_date=end_date,
            )
            if not observations:
                raise ValueError(f"No observations returned for {series.series_id}.")

            normalized_observations = (
                self.series_transform_service.normalize_to_index(observations) if normalize else None
            )
            total_growth = self.series_statistics_service.calculate_total_growth_pct(observations)
            cagr = self.series_statistics_service.calculate_cagr_pct(observations)
            latest_value, latest_date = self.series_statistics_service.latest_value(observations)

            coverage_start = observations[0].date if coverage_start is None else min(coverage_start, observations[0].date)
            coverage_end = observations[-1].date if coverage_end is None else max(coverage_end, observations[-1].date)
            if latest_date is not None:
                latest_observation_date = (
                    latest_date if latest_observation_date is None else max(latest_observation_date, latest_date)
                )

            series_results.append(
                SeriesAnalysis(
                    series=series,
                    observations=observations,
                    transformed_observations=normalized_observations,
                    total_growth_pct=total_growth,
                    compound_annual_growth_rate_pct=cagr,
                    latest_value=latest_value,
                    latest_observation_date=latest_date,
                )
            )

        recession_periods = []
        try:
            recession_observations = self.fred_client.get_series_observations(
                "USREC",
                start_date=coverage_start,
                end_date=coverage_end,
            )
            recession_periods = self.series_statistics_service.derive_recession_periods(recession_observations)
        except Exception as exc:  # pragma: no cover
            warnings.append(f"Unable to load recession shading series: {exc}")

        derived_metrics = []
        first, second = series_results
        if first.total_growth_pct is not None and second.total_growth_pct is not None:
            derived_metrics.append(
                DerivedMetric(
                    name="growth_difference_pct",
                    value=round(first.total_growth_pct - second.total_growth_pct, 4),
                    unit="percentage points",
                    description=(
                        f"Positive values indicate {first.series.geography} grew faster than {second.series.geography}."
                    ),
                )
            )

        if first.latest_value is not None and second.latest_value not in (None, 0):
            derived_metrics.append(
                DerivedMetric(
                    name="latest_size_ratio",
                    value=round(first.latest_value / second.latest_value, 4),
                    unit="x",
                    description=(
                        f"The latest observed GDP level ratio of {first.series.geography} to {second.series.geography}."
                    ),
                )
            )

        analysis = AnalysisResult(
            series_results=series_results,
            derived_metrics=derived_metrics,
            warnings=warnings,
            latest_observation_date=latest_observation_date,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
        )

        chart = self.chart_service.build_state_gdp_chart(
            series_results=series_results,
            start_year=coverage_start.year if coverage_start else start_date.year,
            end_year=coverage_end.year if coverage_end else (end_date.year if end_date else start_date.year),
            normalize=normalize,
            recession_periods=recession_periods,
        )
        answer_text = self.answer_service.write_state_gdp_comparison(analysis, normalize=normalize)

        return QueryResponse(
            intent=intent,
            analysis=analysis,
            chart=chart,
            answer_text=answer_text,
        )
