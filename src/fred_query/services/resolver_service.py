from __future__ import annotations

from fred_query.schemas.resolved_series import ResolvedSeries
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

    def resolve_state_gdp_series(self, state_name: str) -> ResolvedSeries:
        state_code = self.resolve_state_code(state_name)
        canonical_state_name = STATE_CODE_TO_NAME[state_code]
        series_id = f"{state_code}RGSP"
        metadata = self.fred_client.get_series_metadata(series_id)

        return ResolvedSeries(
            series_id=series_id,
            title=metadata.title,
            geography=canonical_state_name,
            indicator="real_gdp",
            units=metadata.units,
            frequency=metadata.frequency,
            seasonal_adjustment=metadata.seasonal_adjustment,
            score=1.0,
            resolution_reason=(
                f"Resolved {state_name} to state code {state_code} and applied the FRED real GDP "
                f"series pattern '{state_code}RGSP'."
            ),
            source_url=metadata.source_url,
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
            return ResolvedSeries(
                series_id=series_id,
                title=metadata.title,
                geography=canonical_state_name,
                indicator=indicator,
                units=metadata.units,
                frequency=metadata.frequency,
                seasonal_adjustment=metadata.seasonal_adjustment,
                score=1.0,
                resolution_reason=(
                    f"Resolved {state_name} to state code {state_code} and applied the FRED series pattern "
                    f"'{state_code}{suffix}' for {indicator.replace('_', ' ')}."
                ),
                source_url=metadata.source_url,
            )

        state_search_text = " ".join(part for part in [canonical_state_name, search_text or indicator_hint] if part)
        matches = self.fred_client.search_series(state_search_text, limit=5)
        if not matches:
            raise ValueError(f"No FRED series matched search text '{state_search_text}'.")

        search_match = matches[0]
        metadata = self.fred_client.get_series_metadata(search_match.series_id)
        return ResolvedSeries(
            series_id=metadata.series_id,
            title=metadata.title,
            geography=canonical_state_name,
            indicator=indicator_hint.strip().lower().replace(" ", "_") or "unknown_indicator",
            units=metadata.units,
            frequency=metadata.frequency,
            seasonal_adjustment=metadata.seasonal_adjustment,
            score=0.8,
            resolution_reason=(
                f"Resolved {canonical_state_name} via FRED search. Top match for '{state_search_text}' was "
                f"{metadata.series_id}."
            ),
            source_url=metadata.source_url,
        )
