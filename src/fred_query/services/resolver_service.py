from __future__ import annotations

from datetime import date
import re

from fred_query.schemas.analysis import ObservationPoint
from fred_query.schemas.resolved_series import ResolvedSeries, SeriesMetadata, SeriesSearchMatch
from fred_query.services.fred_client import FREDClient
from fred_query.services.series_match_scorer import (
    build_match_score_context_from_parts,
    extract_candidate_features,
    is_base_price_index,
    is_plain_inflation_request,
    has_specialized_inflation_variant,
    score_candidate,
)


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

    _SEARCH_CANDIDATE_LIMIT = 15
    _RANKING_WEIGHTS = {
        "frequency_match": 1.75,
        "frequency_mismatch": 0.75,
        "geography_exact_match": 3.0,
        "geography_partial_match": 1.5,
        "geography_missing_penalty": 1.0,
        "indicator_exact_phrase_match": 2.5,
        "indicator_title_term_match": 2.0,
        "indicator_full_text_term_match": 1.0,
        "plain_inflation_base_index_bonus": 3.0,
        "plain_inflation_specialized_penalty": 2.0,
        "plain_inflation_cpi_bonus": 1.0,
        "plain_inflation_pce_bonus": 0.5,
        "plain_inflation_breakeven_penalty": 2.0,
        "search_rank_base_bonus": 2.0,
        "search_rank_decay": 0.15,
        "confidence_single_candidate": 0.72,
        "confidence_close_call": 0.6,
        "confidence_moderate_gap": 0.78,
        "confidence_clear_gap": 0.92,
        "confidence_moderate_gap_threshold": 2.0,
        "confidence_clear_gap_threshold": 5.0,
    }
    _STOP_WORDS = {
        "a",
        "an",
        "and",
        "for",
        "in",
        "of",
        "the",
        "to",
        "united",
        "states",
    }
    _FREQUENCY_TERMS = {
        "daily": ("d", "daily"),
        "weekly": ("w", "weekly"),
        "monthly": ("m", "monthly"),
        "quarterly": ("q", "quarterly"),
        "annual": ("a", "annual"),
        "yearly": ("a", "annual"),
    }

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

    @classmethod
    def _tokenize(cls, value: str | None) -> list[str]:
        if not value:
            return []
        return re.findall(r"[A-Za-z0-9]+", value.lower())

    @classmethod
    def _significant_terms(cls, value: str | None) -> list[str]:
        return [
            token
            for token in cls._tokenize(value)
            if len(token) >= 3 and token not in cls._STOP_WORDS
        ]

    @classmethod
    def _candidate_text(cls, candidate: SeriesSearchMatch) -> str:
        return " ".join(
            part
            for part in [
                candidate.series_id,
                candidate.title,
                candidate.units or "",
                candidate.frequency or "",
                candidate.seasonal_adjustment or "",
                candidate.notes or "",
            ]
            if part
        ).lower()

    @classmethod
    def _frequency_score(cls, candidate: SeriesSearchMatch, *, query_text: str) -> float:
        normalized_frequency = (candidate.frequency or "").strip().lower()
        if not normalized_frequency:
            return 0.0

        score = 0.0
        for term, aliases in cls._FREQUENCY_TERMS.items():
            if term not in query_text:
                continue
            if any(alias in normalized_frequency for alias in aliases):
                score += cls._RANKING_WEIGHTS["frequency_match"]
            else:
                score -= cls._RANKING_WEIGHTS["frequency_mismatch"]
        return score

    @classmethod
    def _geography_score(
        cls,
        candidate: SeriesSearchMatch,
        *,
        geography: str,
        query_text: str,
    ) -> float:
        normalized_geography = geography.strip().lower()
        if not normalized_geography or normalized_geography == "unspecified":
            return 0.0
        if normalized_geography in {"united states", "u.s.", "us", "national"}:
            return 0.0

        candidate_text = cls._candidate_text(candidate)
        geography_terms = cls._significant_terms(geography)
        if not geography_terms:
            return 0.0

        matched_terms = sum(1 for term in geography_terms if term in candidate_text)
        if matched_terms == len(geography_terms):
            return cls._RANKING_WEIGHTS["geography_exact_match"]
        if matched_terms > 0:
            return cls._RANKING_WEIGHTS["geography_partial_match"]
        if any(term in query_text for term in geography_terms):
            return -cls._RANKING_WEIGHTS["geography_missing_penalty"]
        return 0.0

    @classmethod
    def _indicator_phrase_score(cls, candidate: SeriesSearchMatch, *, indicator: str) -> float:
        phrase = indicator.strip().lower()
        if not phrase or phrase == "unknown_indicator":
            return 0.0

        candidate_text = cls._candidate_text(candidate)
        if phrase in candidate_text:
            return cls._RANKING_WEIGHTS["indicator_exact_phrase_match"]

        terms = cls._significant_terms(indicator)
        if not terms:
            return 0.0

        title_text = f"{candidate.series_id} {candidate.title}".lower()
        title_matches = sum(1 for term in terms if term in title_text)
        full_matches = sum(1 for term in terms if term in candidate_text)
        if title_matches >= max(1, min(2, len(terms))):
            return cls._RANKING_WEIGHTS["indicator_title_term_match"]
        if full_matches >= max(1, min(2, len(terms))):
            return cls._RANKING_WEIGHTS["indicator_full_text_term_match"]
        return 0.0

    @classmethod
    def _semantic_profile_score(
        cls,
        candidate: SeriesSearchMatch,
        *,
        search_text: str,
        indicator: str,
    ) -> float:
        search_variants = [value for value in [search_text, indicator] if value]
        if is_plain_inflation_request(search_variants):
            score = 0.0
            if is_base_price_index(candidate):
                score += cls._RANKING_WEIGHTS["plain_inflation_base_index_bonus"]
            if has_specialized_inflation_variant(candidate):
                score -= cls._RANKING_WEIGHTS["plain_inflation_specialized_penalty"]
            candidate_features = extract_candidate_features(candidate)
            if candidate_features.has_cpi:
                score += cls._RANKING_WEIGHTS["plain_inflation_cpi_bonus"]
            elif candidate_features.has_pce:
                score += cls._RANKING_WEIGHTS["plain_inflation_pce_bonus"]
            candidate_text = cls._candidate_text(candidate)
            if "breakeven" in candidate_text:
                score -= cls._RANKING_WEIGHTS["plain_inflation_breakeven_penalty"]
            return score
        return 0.0

    def _rank_search_matches(
        self,
        *,
        search_text: str,
        geography: str,
        indicator: str,
    ) -> list[tuple[float, SeriesSearchMatch]]:
        matches = self.fred_client.search_series(search_text, limit=self._SEARCH_CANDIDATE_LIMIT)
        if not matches:
            return []

        original_query = " ".join(
            value
            for value in [indicator, geography, search_text]
            if value and value != "unknown_indicator" and value != "Unspecified"
        )
        context = build_match_score_context_from_parts(
            search_text=search_text,
            original_query=original_query or search_text,
        )
        query_text = " ".join(
            value.lower()
            for value in [search_text, geography, indicator]
            if value and value not in {"unknown_indicator", "Unspecified"}
        )

        ranked: list[tuple[float, SeriesSearchMatch]] = []
        for rank, candidate in enumerate(matches):
            score = max(
                0.0,
                self._RANKING_WEIGHTS["search_rank_base_bonus"]
                - (rank * self._RANKING_WEIGHTS["search_rank_decay"]),
            )
            if context is not None:
                score += score_candidate(candidate, context=context)
            score += self._frequency_score(candidate, query_text=query_text)
            score += self._geography_score(candidate, geography=geography, query_text=query_text)
            score += self._indicator_phrase_score(candidate, indicator=indicator)
            score += self._semantic_profile_score(candidate, search_text=search_text, indicator=indicator)
            ranked.append((score, candidate))

        ranked.sort(
            key=lambda item: (
                item[0],
                item[1].popularity or 0,
                item[1].title,
            ),
            reverse=True,
        )
        return ranked

    @classmethod
    def _confidence_from_rank_gap(cls, ranked_matches: list[tuple[float, SeriesSearchMatch]]) -> float:
        if len(ranked_matches) == 1:
            return cls._RANKING_WEIGHTS["confidence_single_candidate"]

        winner_score = ranked_matches[0][0]
        runner_up_score = ranked_matches[1][0]
        margin = winner_score - runner_up_score

        if margin >= cls._RANKING_WEIGHTS["confidence_clear_gap_threshold"]:
            return cls._RANKING_WEIGHTS["confidence_clear_gap"]
        if margin >= cls._RANKING_WEIGHTS["confidence_moderate_gap_threshold"]:
            return cls._RANKING_WEIGHTS["confidence_moderate_gap"]
        return cls._RANKING_WEIGHTS["confidence_close_call"]

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

        ranked_matches = self._rank_search_matches(
            search_text=search_text,
            geography=geography,
            indicator=indicator,
        )
        if not ranked_matches:
            raise ValueError(f"No FRED series matched search text '{search_text}'.")

        winner_score, search_match = ranked_matches[0]
        metadata = self.fred_client.get_series_metadata(search_match.series_id)
        normalized_score = self._confidence_from_rank_gap(ranked_matches)
        resolution_reason = (
            search_resolution_reason
            or "Resolved the query via reranked FRED search candidates. Best match from the top {candidate_count} hits was {series_id}."
        ).format(
            geography=geography,
            indicator=indicator,
            search_text=search_text,
            series_id=metadata.series_id,
            title=metadata.title,
            candidate_count=len(ranked_matches),
        )
        return (
            self.build_resolved_series(
                metadata,
                geography=geography,
                indicator=indicator,
                score=normalized_score,
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
