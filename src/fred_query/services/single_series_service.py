from __future__ import annotations

from datetime import date, timedelta

from fred_query.schemas.analysis import AnalysisResult, DerivedMetric, QueryIntent, QueryResponse, SeriesAnalysis
from fred_query.schemas.resolved_series import ResolvedSeries
from fred_query.services.answer_service import AnswerService
from fred_query.services.chart_service import ChartService
from fred_query.services.fred_client import FREDClient
from fred_query.services.transform_service import TransformService


class SingleSeriesLookupService:
    """Deterministic single-series lookup based on a FRED series ID or search phrase."""

    def __init__(
        self,
        fred_client: FREDClient,
        *,
        transform_service: TransformService | None = None,
        chart_service: ChartService | None = None,
        answer_service: AnswerService | None = None,
    ) -> None:
        self.fred_client = fred_client
        self.transform_service = transform_service or TransformService()
        self.chart_service = chart_service or ChartService()
        self.answer_service = answer_service or AnswerService()

    @staticmethod
    def _default_start_date() -> date:
        return date.today() - timedelta(days=365 * 10)

    def lookup(self, intent: QueryIntent) -> QueryResponse:
        start_date = intent.start_date or self._default_start_date()
        end_date = intent.end_date

        if intent.series_id:
            search_match = None
            metadata = self.fred_client.get_series_metadata(intent.series_id)
        else:
            search_text = intent.search_text or " ".join(intent.indicators)
            matches = self.fred_client.search_series(search_text, limit=5)
            if not matches:
                raise ValueError(f"No FRED series matched search text '{search_text}'.")
            search_match = matches[0]
            metadata = self.fred_client.get_series_metadata(search_match.series_id)

        resolved_series = ResolvedSeries(
            series_id=metadata.series_id,
            title=metadata.title,
            geography=intent.geographies[0].name if intent.geographies else "Unspecified",
            indicator=intent.indicators[0] if intent.indicators else "unknown_indicator",
            units=metadata.units,
            frequency=metadata.frequency,
            seasonal_adjustment=metadata.seasonal_adjustment,
            score=1.0 if intent.series_id else 0.8,
            resolution_reason=(
                f"Used explicit series ID {metadata.series_id}."
                if intent.series_id
                else f"Resolved the query via FRED search. Top match was {metadata.series_id}."
            ),
            source_url=metadata.source_url,
        )

        observations = self.fred_client.get_series_observations(
            metadata.series_id,
            start_date=start_date,
            end_date=end_date,
        )
        if not observations:
            raise ValueError(f"No observations returned for {metadata.series_id}.")

        normalized_observations = (
            self.transform_service.normalize_to_index(observations) if intent.normalization else None
        )
        total_growth = self.transform_service.calculate_total_growth_pct(observations)
        latest_value, latest_date = self.transform_service.latest_value(observations)
        recession_periods = []
        try:
            recession_observations = self.fred_client.get_series_observations(
                "USREC",
                start_date=observations[0].date,
                end_date=observations[-1].date,
            )
            recession_periods = self.transform_service.derive_recession_periods(recession_observations)
        except Exception:
            recession_periods = []

        series_analysis = SeriesAnalysis(
            series=resolved_series,
            observations=observations,
            transformed_observations=normalized_observations,
            total_growth_pct=total_growth,
            compound_annual_growth_rate_pct=self.transform_service.calculate_cagr_pct(observations),
            latest_value=latest_value,
            latest_observation_date=latest_date,
        )
        analysis = AnalysisResult(
            series_results=[series_analysis],
            derived_metrics=[
                DerivedMetric(
                    name="top_search_match",
                    value=search_match.series_id if search_match is not None else metadata.series_id,
                    description="The series selected for execution.",
                )
            ],
            latest_observation_date=latest_date,
            coverage_start=observations[0].date,
            coverage_end=observations[-1].date,
        )
        chart = self.chart_service.build_single_series_chart(
            series_result=series_analysis,
            start_year=observations[0].date.year,
            end_year=observations[-1].date.year,
            normalize=intent.normalization,
            recession_periods=recession_periods,
        )
        answer_text = self.answer_service.write_single_series_lookup(analysis, normalize=intent.normalization)
        return QueryResponse(intent=intent, analysis=analysis, chart=chart, answer_text=answer_text)
