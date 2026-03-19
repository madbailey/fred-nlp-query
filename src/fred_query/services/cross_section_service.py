from __future__ import annotations

from datetime import date

from fred_query.schemas.analysis import AnalysisResult, DerivedMetric, ObservationPoint, QueryResponse, SeriesAnalysis
from fred_query.schemas.intent import ComparisonMode, CrossSectionScope, GeographyType, QueryIntent
from fred_query.schemas.resolved_series import ResolvedSeries
from fred_query.services.answer_service import AnswerService
from fred_query.services.cross_section_intent_service import CrossSectionIntentService
from fred_query.services.chart_service import ChartService
from fred_query.services.fred_client import FREDClient
from fred_query.services.resolver_service import ResolverService, STATE_CODE_TO_NAME


class CrossSectionService:
    """Deterministic point-in-time and ranked cross-section analysis."""

    def __init__(
        self,
        fred_client: FREDClient,
        *,
        resolver_service: ResolverService | None = None,
        chart_service: ChartService | None = None,
        answer_service: AnswerService | None = None,
    ) -> None:
        self.fred_client = fred_client
        self.resolver_service = resolver_service or ResolverService(fred_client)
        self.chart_service = chart_service or ChartService()
        self.answer_service = answer_service or AnswerService()

    @staticmethod
    def _indicator_text(intent: QueryIntent) -> str:
        if intent.search_text:
            return intent.search_text
        if intent.indicators:
            return intent.indicators[0]
        if intent.series_id:
            return intent.series_id
        return intent.original_query or "economic indicator"

    @staticmethod
    def _indicator_slug(indicator_text: str) -> str:
        return indicator_text.strip().lower().replace(" ", "_") or "unknown_indicator"

    @staticmethod
    def _display_label(series: ResolvedSeries) -> str:
        return series.geography if series.geography and series.geography != "Unspecified" else series.series_id

    @staticmethod
    def _snapshot_basis(observation_date: date | None) -> str:
        if observation_date is None:
            return "Latest available observation"
        return f"Latest observation on or before {observation_date.isoformat()}"

    def _resolve_single_series(self, intent: QueryIntent, indicator_text: str) -> ResolvedSeries:
        if intent.series_id:
            metadata = self.fred_client.get_series_metadata(intent.series_id)
            return ResolvedSeries(
                series_id=metadata.series_id,
                title=metadata.title,
                geography=intent.geographies[0].name if intent.geographies else "Unspecified",
                indicator=self._indicator_slug(indicator_text),
                units=metadata.units,
                frequency=metadata.frequency,
                seasonal_adjustment=metadata.seasonal_adjustment,
                score=1.0,
                resolution_reason=f"Used explicit series ID {metadata.series_id}.",
                source_url=metadata.source_url,
            )

        matches = self.fred_client.search_series(indicator_text, limit=5)
        if not matches:
            raise ValueError(f"No FRED series matched search text '{indicator_text}'.")

        search_match = matches[0]
        metadata = self.fred_client.get_series_metadata(search_match.series_id)
        return ResolvedSeries(
            series_id=metadata.series_id,
            title=metadata.title,
            geography=intent.geographies[0].name if intent.geographies else "Unspecified",
            indicator=self._indicator_slug(indicator_text),
            units=metadata.units,
            frequency=metadata.frequency,
            seasonal_adjustment=metadata.seasonal_adjustment,
            score=0.8,
            resolution_reason=f"Resolved the query via FRED search. Top match was {metadata.series_id}.",
            source_url=metadata.source_url,
        )

    def _resolve_geography_series(self, intent: QueryIntent, indicator_text: str) -> list[ResolvedSeries]:
        resolved_series: list[ResolvedSeries] = []
        for geography in intent.geographies:
            is_state = geography.geography_type == GeographyType.STATE
            if not is_state:
                try:
                    self.resolver_service.resolve_state_code(geography.name)
                except ValueError:
                    is_state = False
                else:
                    is_state = True

            if is_state:
                resolved_series.append(
                    self.resolver_service.resolve_state_indicator_series(
                        geography.name,
                        indicator_hint=indicator_text,
                        search_text=intent.search_text,
                    )
                )
                continue

            geography_search = " ".join(
                part for part in [geography.name, intent.search_text or indicator_text] if part
            )
            matches = self.fred_client.search_series(geography_search, limit=5)
            if not matches:
                raise ValueError(f"No FRED series matched search text '{geography_search}'.")

            search_match = matches[0]
            metadata = self.fred_client.get_series_metadata(search_match.series_id)
            resolved_series.append(
                ResolvedSeries(
                    series_id=metadata.series_id,
                    title=metadata.title,
                    geography=geography.name,
                    indicator=self._indicator_slug(indicator_text),
                    units=metadata.units,
                    frequency=metadata.frequency,
                    seasonal_adjustment=metadata.seasonal_adjustment,
                    score=0.8,
                    resolution_reason=(
                        f"Resolved {geography.name} via FRED search. Top match for '{geography_search}' "
                        f"was {metadata.series_id}."
                    ),
                    source_url=metadata.source_url,
                )
            )
        return resolved_series

    def _resolve_series(self, intent: QueryIntent, scope: CrossSectionScope, indicator_text: str) -> list[ResolvedSeries]:
        if scope == CrossSectionScope.STATES:
            return [
                self.resolver_service.resolve_state_indicator_series(
                    state_name,
                    indicator_hint=indicator_text,
                    search_text=intent.search_text,
                )
                for state_name in STATE_CODE_TO_NAME.values()
            ]
        if scope == CrossSectionScope.PROVIDED_GEOGRAPHIES:
            return self._resolve_geography_series(intent, indicator_text)
        return [self._resolve_single_series(intent, indicator_text)]

    def _fetch_snapshot_point(
        self,
        series: ResolvedSeries,
        *,
        observation_date: date | None,
        frequency: str | None,
    ) -> ObservationPoint:
        aggregation_method = "avg" if frequency else None
        observations = self.fred_client.get_series_observations(
            series.series_id,
            end_date=observation_date,
            frequency=frequency,
            aggregation_method=aggregation_method,
            limit=1,
            sort_order="desc",
        )
        if not observations:
            date_text = observation_date.isoformat() if observation_date is not None else "the latest date"
            raise ValueError(f"No observations returned for {series.series_id} at {date_text}.")
        return observations[0]

    @staticmethod
    def _sort_results(
        series_results: list[SeriesAnalysis],
        *,
        descending: bool,
    ) -> list[SeriesAnalysis]:
        return sorted(
            series_results,
            key=lambda result: result.latest_value if result.latest_value is not None else float("-inf"),
            reverse=descending,
        )

    @staticmethod
    def _chart_title(scope: CrossSectionScope, series_results: list[SeriesAnalysis], indicator_text: str) -> str:
        if scope == CrossSectionScope.STATES:
            return f"State Ranking: {indicator_text.title()}"
        if scope == CrossSectionScope.PROVIDED_GEOGRAPHIES and len(series_results) > 1:
            labels = [result.series.geography for result in series_results[:3]]
            label_text = ", ".join(labels[:2]) if len(labels) == 2 else ", ".join(labels[:3])
            return f"Cross-Section Snapshot: {label_text}"
        return series_results[0].series.title

    def analyze(self, intent: QueryIntent) -> QueryResponse:
        response_intent = intent.model_copy(deep=True)
        response_intent.comparison_mode = ComparisonMode.CROSS_SECTION
        CrossSectionIntentService.apply_defaults(response_intent)
        scope = response_intent.cross_section_scope or CrossSectionScope.SINGLE_SERIES
        response_intent.cross_section_scope = scope

        indicator_text = self._indicator_text(response_intent)
        observation_date = response_intent.observation_date or response_intent.end_date
        response_intent.observation_date = observation_date

        resolved_series = self._resolve_series(response_intent, scope, indicator_text)
        if scope == CrossSectionScope.SINGLE_SERIES and resolved_series:
            response_intent.series_id = resolved_series[0].series_id
            response_intent.search_text = response_intent.search_text or indicator_text
        series_results: list[SeriesAnalysis] = []
        warnings: list[str] = []

        for resolved in resolved_series:
            try:
                point = self._fetch_snapshot_point(
                    resolved,
                    observation_date=observation_date,
                    frequency=response_intent.frequency,
                )
            except ValueError as exc:
                if scope == CrossSectionScope.SINGLE_SERIES:
                    raise
                warnings.append(str(exc))
                continue

            series_results.append(
                SeriesAnalysis(
                    series=resolved,
                    observations=[point],
                    latest_value=point.value,
                    latest_observation_date=point.date,
                )
            )

        if not series_results:
            raise ValueError("I could not resolve any cross-section observations for the requested query.")

        ranked_results = self._sort_results(
            series_results,
            descending=response_intent.sort_descending,
        )
        display_limit, display_selection_basis = CrossSectionIntentService.display_limit_details(
            response_intent,
            scope=scope,
            result_count=len(ranked_results),
        )
        displayed_results = ranked_results[:display_limit]

        response_intent.rank_limit = display_limit if len(displayed_results) != len(ranked_results) else response_intent.rank_limit
        leader = ranked_results[0]
        snapshot_basis = self._snapshot_basis(observation_date)
        rank_label = "highest" if response_intent.sort_descending else "lowest"

        derived_metrics = [
            DerivedMetric(
                name="resolved_series_count",
                value=len(ranked_results),
                unit="series",
                description="Series included in the ranked cross-section before any display cap was applied.",
            ),
            DerivedMetric(
                name="displayed_series_count",
                value=len(displayed_results),
                unit="series",
                description="Series shown in the ranked bar chart.",
            ),
            DerivedMetric(
                name="display_selection_basis",
                value=display_selection_basis,
                description="Whether the displayed slice came from an explicit request, a contextual default, or the full result set.",
            ),
            DerivedMetric(
                name="snapshot_basis",
                value=snapshot_basis,
                description="Observation timing used for the cross-section snapshot.",
            ),
            DerivedMetric(
                name="rank_leader",
                value=self._display_label(leader.series),
                description=f"The geography or series with the {rank_label} observed value in the ranked snapshot.",
            ),
        ]

        if leader.latest_value is not None:
            derived_metrics.append(
                DerivedMetric(
                    name="rank_leader_value",
                    value=round(leader.latest_value, 4),
                    unit=leader.series.units,
                    description=f"The {rank_label} observed value in the ranked snapshot.",
                )
            )

        coverage_dates = [result.latest_observation_date for result in displayed_results if result.latest_observation_date is not None]
        analysis = AnalysisResult(
            series_results=displayed_results,
            derived_metrics=derived_metrics,
            warnings=warnings,
            latest_observation_date=max(coverage_dates) if coverage_dates else None,
            coverage_start=min(coverage_dates) if coverage_dates else None,
            coverage_end=max(coverage_dates) if coverage_dates else None,
        )
        chart = self.chart_service.build_cross_section_chart(
            series_results=displayed_results,
            title=self._chart_title(scope, displayed_results, indicator_text),
            subtitle=self._chart_subtitle(
                snapshot_basis=snapshot_basis,
                displayed_count=len(displayed_results),
                result_count=len(ranked_results),
                display_selection_basis=display_selection_basis,
            ),
            y_axis_title=displayed_results[0].series.units,
        )
        answer_text = self.answer_service.write_cross_section(analysis, intent=response_intent)
        return QueryResponse(
            intent=response_intent,
            analysis=analysis,
            chart=chart,
            answer_text=answer_text,
        )

    @staticmethod
    def _chart_subtitle(
        *,
        snapshot_basis: str,
        displayed_count: int,
        result_count: int,
        display_selection_basis: str,
    ) -> str:
        if display_selection_basis == "comparison_context":
            return (
                f"{snapshot_basis}. Showing {displayed_count} of {result_count} series for comparison context."
            )
        if display_selection_basis == "explicit_request":
            return f"{snapshot_basis}. Showing the requested {displayed_count} of {result_count} series."
        return f"{snapshot_basis}. Showing all {result_count} series."
