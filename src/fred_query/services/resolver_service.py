from __future__ import annotations

from datetime import date

from fred_query.schemas.analysis import ObservationPoint
from fred_query.schemas.resolved_series import ResolvedSeries, SeriesMetadata, SeriesSearchMatch
from fred_query.services.fred_client import FREDClient


STATE_NAME_TO_CODE = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "puerto rico": "PR",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}

STATE_CODE_TO_NAME = {code: name.title() for name, code in STATE_NAME_TO_CODE.items()}
STATE_SERIES_PATTERNS = {
    "real gdp": ("RGSP", "real_gdp"),
    "gdp": ("RGSP", "real_gdp"),
    "gross domestic product": ("RGSP", "real_gdp"),
    "unemployment rate": ("UR", "unemployment_rate"),
    "unemployment": ("UR", "unemployment_rate"),
    "jobless rate": ("UR", "unemployment_rate"),
}


class ResolverService:
    """Resolve deterministic series mappings for the first workflow."""

    def __init__(self, fred_client: FREDClient) -> None:
        self.fred_client = fred_client

    @staticmethod
    def resolve_state_code(state_name: str) -> str:
        normalized = state_name.strip().lower()
        if normalized in STATE_NAME_TO_CODE:
            return STATE_NAME_TO_CODE[normalized]

        uppercase = state_name.strip().upper()
        if uppercase in STATE_CODE_TO_NAME:
            return uppercase

        raise ValueError(f"Unrecognized state: {state_name}")

    @staticmethod
    def build_resolved_series(
        metadata: SeriesMetadata,
        *,
        geography: str,
        indicator: str,
        score: float,
        resolution_reason: str,
    ) -> ResolvedSeries:
        return ResolvedSeries(
            series_id=metadata.series_id,
            title=metadata.title,
            geography=geography,
            indicator=indicator,
            units=metadata.units,
            frequency=metadata.frequency,
            seasonal_adjustment=metadata.seasonal_adjustment,
            score=score,
            resolution_reason=resolution_reason,
            source_url=metadata.source_url,
        )

    def resolve_series(
        self,
        *,
        explicit_series_id: str | None = None,
        search_text: str | None = None,
        geography: str = "Unspecified",
        indicator: str = "unknown_indicator",
        no_target_message: str | None = None,
        search_resolution_reason: str | None = None,
    ) -> tuple[ResolvedSeries, SeriesMetadata, SeriesSearchMatch | None]:
        if explicit_series_id:
            metadata = self.fred_client.get_series_metadata(explicit_series_id)
            return (
                self.build_resolved_series(
                    metadata,
                    geography=geography,
                    indicator=indicator,
                    score=1.0,
                    resolution_reason=f"Used explicit series ID {metadata.series_id}.",
                ),
                metadata,
                None,
            )

        if not search_text:
            raise ValueError(no_target_message or "I need a resolvable series target before I can continue.")

        matches = self.fred_client.search_series(search_text, limit=5)
        if not matches:
            raise ValueError(f"No FRED series matched search text '{search_text}'.")

        search_match = matches[0]
        metadata = self.fred_client.get_series_metadata(search_match.series_id)
        resolution_reason = (
            search_resolution_reason or "Resolved the query via FRED search. Top match was {series_id}."
        ).format(
            geography=geography,
            indicator=indicator,
            search_text=search_text,
            series_id=metadata.series_id,
            title=metadata.title,
        )
        return (
            self.build_resolved_series(
                metadata,
                geography=geography,
                indicator=indicator,
                score=0.8,
                resolution_reason=resolution_reason,
            ),
            metadata,
            search_match,
        )

    def get_required_observations(
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
        request_kwargs: dict[str, object] = {}
        if start_date is not None:
            request_kwargs["start_date"] = start_date
        if end_date is not None:
            request_kwargs["end_date"] = end_date
        if frequency is not None:
            request_kwargs["frequency"] = frequency
        if aggregation_method is not None:
            request_kwargs["aggregation_method"] = aggregation_method
        if limit is not None:
            request_kwargs["limit"] = limit
        if sort_order is not None:
            request_kwargs["sort_order"] = sort_order

        observations = self.fred_client.get_series_observations(series_id, **request_kwargs)
        if observations:
            return observations
        raise ValueError(empty_result_message or f"No observations returned for {series_id}.")

    def resolve_state_gdp_series(self, state_name: str) -> ResolvedSeries:
        state_code = self.resolve_state_code(state_name)
        canonical_state_name = STATE_CODE_TO_NAME[state_code]
        series_id = f"{state_code}RGSP"
        metadata = self.fred_client.get_series_metadata(series_id)

        return self.build_resolved_series(
            metadata,
            geography=canonical_state_name,
            indicator="real_gdp",
            score=1.0,
            resolution_reason=(
                f"Resolved {state_name} to state code {state_code} and applied the FRED real GDP "
                f"series pattern '{state_code}RGSP'."
            ),
        )

    @staticmethod
    def _state_series_pattern(indicator_hint: str) -> tuple[str, str] | None:
        normalized = indicator_hint.strip().lower()
        for phrase, mapping in STATE_SERIES_PATTERNS.items():
            if phrase in normalized:
                return mapping
        return None

    def resolve_state_indicator_series(
        self,
        state_name: str,
        *,
        indicator_hint: str,
        search_text: str | None = None,
    ) -> ResolvedSeries:
        state_code = self.resolve_state_code(state_name)
        canonical_state_name = STATE_CODE_TO_NAME[state_code]
        pattern = self._state_series_pattern(indicator_hint)
        if pattern is not None:
            suffix, indicator = pattern
            series_id = f"{state_code}{suffix}"
            metadata = self.fred_client.get_series_metadata(series_id)
            return self.build_resolved_series(
                metadata,
                geography=canonical_state_name,
                indicator=indicator,
                score=1.0,
                resolution_reason=(
                    f"Resolved {state_name} to state code {state_code} and applied the FRED series pattern "
                    f"'{state_code}{suffix}' for {indicator.replace('_', ' ')}."
                ),
            )

        state_search_text = " ".join(part for part in [canonical_state_name, search_text or indicator_hint] if part)
        resolved, _, _ = self.resolve_series(
            search_text=state_search_text,
            geography=canonical_state_name,
            indicator=indicator_hint.strip().lower().replace(" ", "_") or "unknown_indicator",
            search_resolution_reason=(
                "Resolved {geography} via FRED search. Top match for '{search_text}' was {series_id}."
            ),
        )
        return resolved
