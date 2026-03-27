from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import re

from fred_query.schemas.analysis import RoutedQueryResponse, RoutedQueryStatus
from fred_query.schemas.intent import ComparisonMode, QueryIntent, TaskType, TransformType
from fred_query.schemas.resolved_series import SeriesSearchMatch
from fred_query.services.comparison_service import StateGDPComparisonService
from fred_query.services.cross_section_service import CrossSectionService
from fred_query.services.fred_client import FREDClient
from fred_query.services.openai_parser_service import OpenAIIntentParser
from fred_query.services.query_session_service import QuerySession
from fred_query.services.relationship_service import RelationshipAnalysisService
from fred_query.services.single_series_service import SingleSeriesLookupService
from fred_query.services.vintage_analysis_service import VintageAnalysisService


@dataclass(frozen=True, slots=True)
class _SessionTarget:
    series_id: str | None = None
    search_text: str | None = None
    indicator: str | None = None


class NaturalLanguageQueryService:
    """Route a natural-language query into deterministic execution."""

    _FREQUENCY_LABELS = {
        "D": "Daily",
        "W": "Weekly",
        "BW": "Biweekly",
        "M": "Monthly",
        "Q": "Quarterly",
        "SA": "Semiannual",
        "A": "Annual",
    }
    _STOP_WORDS = {
        "a",
        "about",
        "all",
        "an",
        "and",
        "another",
        "any",
        "are",
        "at",
        "be",
        "between",
        "data",
        "do",
        "economy",
        "economic",
        "for",
        "from",
        "in",
        "into",
        "is",
        "like",
        "measure",
        "me",
        "of",
        "on",
        "or",
        "question",
        "relationship",
        "series",
        "show",
        "since",
        "than",
        "that",
        "the",
        "this",
        "to",
        "use",
        "used",
        "want",
        "what",
        "which",
        "would",
        "you",
    }
    _INSTRUMENT_TERMS = {
        "bond",
        "bonds",
        "coupon",
        "investment",
        "maturity",
        "note",
        "notes",
        "security",
        "securities",
        "treasury",
        "yield",
    }
    _FOLLOW_UP_TOKENS = {
        "again",
        "also",
        "another",
        "instead",
        "it",
        "same",
        "that",
        "them",
        "then",
        "those",
    }
    _FOLLOW_UP_LEADING_TOKENS = {"also", "now", "then", "instead"}
    _COMPARISON_TERMS = ("compare", "comparison", "versus", "vs", "against")
    _RELATIONSHIP_TERMS = ("correlation", "correlate", "co-movement", "lead", "lag", "relationship")
    _TRANSFORM_TERMS = (
        "index",
        "level",
        "levels",
        "mom",
        "moving average",
        "normalized",
        "percent change",
        "qoq",
        "rolling",
        "standard deviation",
        "stddev",
        "volatility",
        "yoy",
        "year over year",
    )
    _LATEST_RESET_TERMS = ("current", "latest", "most recent", "now", "today")
    _ASCENDING_TERMS = ("bottom", "least", "lowest", "smallest")
    _DESCENDING_TERMS = ("highest", "largest", "most", "top")

    def __init__(
        self,
        *,
        parser: OpenAIIntentParser,
        fred_client: FREDClient,
        state_gdp_service: StateGDPComparisonService | None = None,
        cross_section_service: CrossSectionService | None = None,
        single_series_service: SingleSeriesLookupService | None = None,
        relationship_service: RelationshipAnalysisService | None = None,
        vintage_analysis_service: VintageAnalysisService | None = None,
    ) -> None:
        self.parser = parser
        self.fred_client = fred_client
        self.state_gdp_service = state_gdp_service or StateGDPComparisonService(fred_client)
        self.cross_section_service = cross_section_service or CrossSectionService(fred_client)
        self.single_series_service = single_series_service or SingleSeriesLookupService(fred_client)
        self.relationship_service = relationship_service or RelationshipAnalysisService(fred_client)
        self.vintage_analysis_service = vintage_analysis_service or VintageAnalysisService(fred_client)

    @staticmethod
    def _default_start_date() -> date:
        return date.today() - timedelta(days=365 * 10)

    @classmethod
    def _tokenize(cls, text: str | None) -> list[str]:
        if not text:
            return []
        return re.findall(r"[A-Za-z0-9]+", text.lower())

    @classmethod
    def _significant_terms(cls, texts: list[str]) -> list[str]:
        seen: set[str] = set()
        terms: list[str] = []
        for text in texts:
            for token in cls._tokenize(text):
                if len(token) < 3 or token in cls._STOP_WORDS:
                    continue
                if token in seen:
                    continue
                seen.add(token)
                terms.append(token)
        return terms

    @classmethod
    def _extract_clarification_examples(cls, question: str | None) -> list[str]:
        if not question:
            return []

        source = question.strip()
        if ":" in source:
            source = source.split(":", maxsplit=1)[1]
        else:
            match = re.search(r"\bmean\b(?P<tail>.+)$", source, flags=re.IGNORECASE)
            if match:
                source = match.group("tail")

        source = re.sub(r"\bor\s+another\b.*$", "", source, flags=re.IGNORECASE).strip(" ?.")
        source = re.sub(r"\bor\s+", ", ", source, flags=re.IGNORECASE)

        examples: list[str] = []
        seen: set[str] = set()
        for part in source.split(","):
            cleaned = re.sub(r"^(and|or)\s+", "", part.strip(), flags=re.IGNORECASE).strip(" ?.")
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered.startswith("another") or lowered.startswith("other"):
                continue
            if lowered in seen:
                continue
            seen.add(lowered)
            examples.append(cleaned)
        return examples[:3]

    def _clarification_search_text(self, intent: QueryIntent) -> str | None:
        search_text = intent.search_text
        if (
            intent.task_type in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS)
            and intent.clarification_target_index is not None
            and intent.clarification_target_index < len(intent.search_texts)
        ):
            search_text = intent.search_texts[intent.clarification_target_index]
        return search_text

    @classmethod
    def _score_candidate(
        cls,
        candidate: SeriesSearchMatch,
        *,
        search_variants: list[str],
        anchor_terms: list[str],
    ) -> float:
        title_text = f"{candidate.series_id} {candidate.title}".lower()
        full_text = " ".join(
            [
                candidate.series_id,
                candidate.title,
                candidate.notes or "",
                candidate.units or "",
                candidate.frequency or "",
            ]
        ).lower()

        score = 0.0
        title_matches = 0
        for term in anchor_terms:
            if term in title_text:
                score += 3.0
                title_matches += 1
            elif term in full_text:
                score += 1.0

        for phrase in search_variants:
            lowered_phrase = phrase.lower().strip()
            if not lowered_phrase:
                continue
            if lowered_phrase in full_text:
                score += 5.0
                continue

            phrase_terms = cls._significant_terms([phrase])
            if phrase_terms:
                matched_terms = sum(1 for term in phrase_terms if term in title_text)
                if matched_terms >= max(1, min(2, len(phrase_terms))):
                    score += 3.5

        if candidate.popularity is not None:
            score += min(candidate.popularity / 25.0, 2.0)

        if not any(term in anchor_terms for term in cls._INSTRUMENT_TERMS):
            penalty_hits = sum(1 for term in cls._INSTRUMENT_TERMS if term in title_text)
            score -= penalty_hits * 1.5

        if title_matches == 0:
            score -= 2.0

        if cls._is_plain_inflation_request(search_variants):
            if cls._is_base_price_index(candidate):
                score += 2.5
            if cls._has_specialized_inflation_variant(candidate):
                score -= 2.0

        return score

    @staticmethod
    def _candidate_title_key(candidate: SeriesSearchMatch) -> str:
        return re.sub(r"\s+", " ", candidate.title.strip().lower())

    @classmethod
    def _dedupe_candidates(cls, candidates: list[SeriesSearchMatch]) -> list[SeriesSearchMatch]:
        deduped: list[SeriesSearchMatch] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = cls._candidate_title_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    @classmethod
    def _dedupe_ranked_candidates(
        cls,
        ranked_candidates: list[tuple[float, SeriesSearchMatch]],
    ) -> list[SeriesSearchMatch]:
        deduped: list[SeriesSearchMatch] = []
        seen: set[str] = set()
        for _, candidate in ranked_candidates:
            key = cls._candidate_title_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    @classmethod
    def _variant_priority_score(cls, candidate: SeriesSearchMatch, variant: str) -> float:
        score = 0.0
        normalized_variant = cls._normalized_text(variant)
        if "inflation" in normalized_variant and cls._is_plain_inflation_request([variant]):
            if cls._is_base_price_index(candidate):
                score += 3.0
            if cls._has_specialized_inflation_variant(candidate):
                score -= 2.5
        return score

    @staticmethod
    def _normalized_text(value: str | None) -> str:
        return (value or "").strip().lower()

    @classmethod
    def _is_plain_inflation_request(cls, search_variants: list[str]) -> bool:
        combined = " ".join(search_variants).lower()
        if "inflation" not in combined:
            return False
        return not any(
            term in combined
            for term in ("core", "trimmed", "breakeven", "deflator", "producer", "annualized", "year over year")
        )

    @classmethod
    def _candidate_has_any(cls, candidate: SeriesSearchMatch, terms: tuple[str, ...]) -> bool:
        text = cls._candidate_text(candidate)
        return any(term in text for term in terms)

    @classmethod
    def _is_base_price_index(cls, candidate: SeriesSearchMatch) -> bool:
        text = cls._candidate_text(candidate)
        if not ("consumer price index" in text or "personal consumption expenditures" in text or re.search(r"\bcpi\b", text) or re.search(r"\bpce\b", text)):
            return False
        return (
            "index" in text
            and not cls._has_specialized_inflation_variant(candidate)
        )

    @classmethod
    def _has_specialized_inflation_variant(cls, candidate: SeriesSearchMatch) -> bool:
        return cls._candidate_has_any(
            candidate,
            (
                "trimmed mean",
                "core",
                "excluding food and energy",
                "less food and energy",
                "annual rate",
                "annualized",
                "% chg",
                "percent change",
                "breakeven",
                "inflation-indexed",
                "producer price",
                "deflator",
            ),
        )

    def _build_clarification_candidates(self, intent: QueryIntent) -> list[SeriesSearchMatch]:
        search_text = self._clarification_search_text(intent)
        if not search_text:
            return []

        example_searches = self._extract_clarification_examples(intent.clarification_question)
        search_variants: list[str] = []
        for value in [*example_searches, search_text]:
            normalized = value.strip()
            if normalized and normalized not in search_variants:
                search_variants.append(normalized)

        anchor_terms = self._significant_terms(
            [
                intent.original_query or "",
                intent.clarification_question or "",
                search_text,
                *example_searches,
            ]
        )

        scored_candidates: dict[str, tuple[float, SeriesSearchMatch]] = {}
        variant_rankings: dict[str, list[tuple[float, SeriesSearchMatch]]] = {}
        for variant_index, variant in enumerate(search_variants):
            try:
                matches = self.fred_client.search_series(variant, limit=6)
            except Exception:
                continue

            for rank, candidate in enumerate(matches):
                score = self._score_candidate(
                    candidate,
                    search_variants=search_variants,
                    anchor_terms=anchor_terms,
                )
                score += max(0.0, 1.5 - (rank * 0.25))
                score += max(0.0, 0.5 - (variant_index * 0.1))
                variant_rankings.setdefault(variant, []).append((score, candidate))

                current = scored_candidates.get(candidate.series_id)
                if current is None or score > current[0]:
                    scored_candidates[candidate.series_id] = (score, candidate)

        ranked = sorted(
            scored_candidates.values(),
            key=lambda item: (
                item[0],
                item[1].popularity or 0,
                item[1].title,
            ),
            reverse=True,
        )

        minimum_score = 5.0 if example_searches else 2.0
        filtered = self._dedupe_candidates([candidate for score, candidate in ranked if score >= minimum_score])
        prioritized: list[SeriesSearchMatch] = []
        prioritized_keys: set[str] = set()
        for example in example_searches:
            example_ranked = sorted(
                variant_rankings.get(example, []),
                key=lambda item: (
                    item[0] + self._variant_priority_score(item[1], example),
                    item[1].popularity or 0,
                    item[1].title,
                ),
                reverse=True,
            )
            for candidate in self._dedupe_ranked_candidates(example_ranked):
                key = self._candidate_title_key(candidate)
                if key in prioritized_keys:
                    continue
                prioritized.append(candidate)
                prioritized_keys.add(key)
                break
        if filtered:
            merged_candidates = prioritized + [
                candidate for candidate in filtered if self._candidate_title_key(candidate) not in prioritized_keys
            ]
            return self._annotate_clarification_candidates(merged_candidates[:4], intent=intent)

        fallback_candidates = prioritized + [
            candidate
            for candidate in self._dedupe_ranked_candidates(ranked)
            if self._candidate_title_key(candidate) not in prioritized_keys
        ]
        if fallback_candidates:
            return self._annotate_clarification_candidates(fallback_candidates[:4], intent=intent)

        return []

    @staticmethod
    def _candidate_text(candidate: SeriesSearchMatch) -> str:
        return " ".join(
            value
            for value in [
                candidate.series_id,
                candidate.title,
                candidate.units or "",
                candidate.frequency or "",
                candidate.seasonal_adjustment or "",
                candidate.notes or "",
            ]
            if value
        ).lower()

    @classmethod
    def _selection_hint_for_candidate(
        cls,
        candidate: SeriesSearchMatch,
        *,
        search_text: str | None,
    ) -> str:
        text = cls._candidate_text(candidate)
        has_core = "core" in text or "less food and energy" in text or "excluding food and energy" in text
        has_pce = "personal consumption expenditures" in text or re.search(r"\bpce\b", text) is not None
        has_cpi = "consumer price index" in text or re.search(r"\bcpi\b", text) is not None
        has_breakeven = (
            "breakeven" in text
            or "inflation compensation" in text
            or "inflation-indexed" in text
            or "treasury" in text
        )
        has_ppi = "producer price" in text or re.search(r"\bppi\b", text) is not None
        has_deflator = "deflator" in text
        has_trimmed = "trimmed mean" in text
        has_change_rate = "% chg" in text or "percent change" in text or "annual rate" in text or "annualized" in text

        if has_trimmed and has_pce:
            return "Pick this if you want trimmed-mean PCE, a smoother Dallas Fed trend measure rather than the standard headline PCE series."
        if has_core and has_pce:
            return "Pick this if you want core PCE inflation, which strips out food and energy and is closely watched by the Fed."
        if has_core and has_cpi:
            return "Pick this if you want core CPI inflation, which strips out food and energy from the consumer price index."
        if has_pce and has_change_rate:
            return "Pick this if you want PCE inflation already expressed as a rate of change rather than as the raw price index."
        if has_cpi and has_change_rate:
            return "Pick this if you want CPI already expressed as a rate of change rather than as the raw price index."
        if has_pce:
            return "Pick this if you want PCE inflation, the consumption-based price measure the Fed often references."
        if has_cpi:
            return "Pick this if you want CPI, the broad consumer inflation measure most people mean by 'inflation'."
        if has_breakeven:
            return "Pick this if you want a market-implied inflation expectation from Treasury pricing, not a realized inflation index."
        if has_ppi:
            return "Pick this if you want producer-price inflation rather than consumer inflation."
        if has_deflator:
            return "Pick this if you want a deflator-style price measure rather than a headline consumer index."
        if has_core:
            return "Pick this if you want a core inflation measure that strips out volatile categories."
        if candidate.frequency and candidate.units:
            return (
                f"Pick this if you want {candidate.frequency.lower()} data reported in {candidate.units.lower()} "
                f"for {search_text or 'the requested measure'}."
            )
        if candidate.frequency:
            return f"Pick this if you want {candidate.frequency.lower()} data for {search_text or 'the requested measure'}."
        return f'Pick this if you want the series titled "{candidate.title}".'

    @classmethod
    def _selection_label_for_candidate(cls, candidate: SeriesSearchMatch) -> str | None:
        text = cls._candidate_text(candidate)
        has_core = "core" in text or "less food and energy" in text or "excluding food and energy" in text
        has_pce = "personal consumption expenditures" in text or re.search(r"\bpce\b", text) is not None
        has_cpi = "consumer price index" in text or re.search(r"\bcpi\b", text) is not None
        has_trimmed = "trimmed mean" in text
        has_breakeven = (
            "breakeven" in text
            or "inflation compensation" in text
            or "inflation-indexed" in text
            or "treasury" in text
        )
        has_ppi = "producer price" in text or re.search(r"\bppi\b", text) is not None
        has_deflator = "deflator" in text

        if has_trimmed and has_pce:
            return "Trimmed Mean PCE"
        if has_core and has_pce:
            return "Core PCE"
        if has_core and has_cpi:
            return "Core CPI"
        if has_pce:
            return "Headline PCE"
        if has_cpi:
            return "Headline CPI"
        if has_breakeven:
            return "Market Inflation Expectations"
        if has_ppi:
            return "Producer Prices"
        if has_deflator:
            return "Price Deflator"
        return None

    @classmethod
    def _selection_badges_for_candidate(cls, candidate: SeriesSearchMatch) -> list[str]:
        badges: list[str] = []
        frequency_label = cls._FREQUENCY_LABELS.get((candidate.frequency or "").upper())
        if frequency_label:
            badges.append(frequency_label)

        units_text = cls._normalized_text(candidate.units)
        if "6-month annualized" in units_text:
            badges.append("6M annualized")
        elif "% chg. from yr. ago" in units_text or "percent change from year ago" in units_text:
            badges.append("YoY rate")
        elif "annual rate" in units_text or "annualized" in units_text:
            badges.append("Annualized rate")
        elif "index" in units_text:
            badges.append("Index level")
        elif "percent" in units_text:
            badges.append("Percent")

        if candidate.seasonal_adjustment:
            badges.append(candidate.seasonal_adjustment)

        return badges[:3]

    def _annotate_clarification_candidates(
        self,
        candidates: list[SeriesSearchMatch],
        *,
        intent: QueryIntent,
    ) -> list[SeriesSearchMatch]:
        search_text = self._clarification_search_text(intent)
        return [
            candidate.model_copy(
                update={
                    "selection_label": self._selection_label_for_candidate(candidate),
                    "selection_hint": self._selection_hint_for_candidate(
                        candidate,
                        search_text=search_text,
                    ),
                    "selection_badges": self._selection_badges_for_candidate(candidate),
                }
            )
            for candidate in candidates
        ]

    @staticmethod
    def _clarification_answer_text(
        intent: QueryIntent,
        *,
        candidate_series: list[SeriesSearchMatch],
    ) -> str:
        question = intent.clarification_question or "I need one clarification before I can query FRED safely."
        if candidate_series:
            return f"{question} Pick one of the series below to continue."
        return question

    @staticmethod
    def _apply_selected_series(intent: QueryIntent, selected_series_ids: list[str | None] | None) -> QueryIntent:
        if not selected_series_ids:
            return intent

        normalized_ids = list(selected_series_ids)
        if intent.task_type in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS):
            target_count = max(2, len(intent.search_texts), len(intent.series_ids), len(normalized_ids))
            intent.series_ids = (intent.series_ids + [None] * target_count)[:target_count]
            for index, series_id in enumerate(normalized_ids):
                if index >= len(intent.series_ids) or not series_id:
                    continue
                intent.series_ids[index] = series_id
                intent.parser_notes.append(
                    f"User selected explicit series ID {series_id} for target {index} from clarification options."
                )
            intent.clarification_needed = False
            intent.clarification_question = None
            intent.clarification_target_index = None
            return intent

        selected_series_id = next((value for value in normalized_ids if value), None)
        if selected_series_id:
            intent.task_type = TaskType.SINGLE_SERIES_LOOKUP
            intent.series_id = selected_series_id
            intent.clarification_needed = False
            intent.clarification_question = None
            intent.clarification_target_index = None
            intent.parser_notes.append(
                f"User selected explicit series ID {selected_series_id} from clarification options."
            )
        return intent

    @staticmethod
    def _session_intent(session_context: QuerySession | None) -> QueryIntent | None:
        if session_context is None or session_context.last_response is None:
            return None
        if session_context.last_response.query_response is not None:
            return session_context.last_response.query_response.intent
        return session_context.last_response.intent

    @classmethod
    def _target_count_for_intent(cls, intent: QueryIntent) -> int:
        if intent.task_type in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS):
            return max(2, len(intent.series_ids), len(intent.search_texts), len(intent.indicators))
        return 1

    @classmethod
    def _extract_targets_from_intent(cls, intent: QueryIntent) -> list[_SessionTarget]:
        targets: list[_SessionTarget] = []
        for index in range(cls._target_count_for_intent(intent)):
            series_id = intent.series_id if index == 0 else None
            search_text = intent.search_text if index == 0 else None
            if index < len(intent.series_ids) and intent.series_ids[index]:
                series_id = intent.series_ids[index]
            if index < len(intent.search_texts) and intent.search_texts[index]:
                search_text = intent.search_texts[index]
            indicator = intent.indicators[index] if index < len(intent.indicators) else None
            if series_id or search_text or indicator:
                targets.append(
                    _SessionTarget(
                        series_id=series_id,
                        search_text=search_text,
                        indicator=indicator,
                    )
                )
        return targets

    @classmethod
    def _resolved_session_targets(cls, session_context: QuerySession | None) -> list[_SessionTarget]:
        intent = cls._session_intent(session_context)
        response = session_context.last_response if session_context is not None else None
        if intent is None or response is None:
            return []

        series_results = []
        if response.query_response is not None:
            series_results = response.query_response.analysis.series_results

        base_targets = cls._extract_targets_from_intent(intent)
        targets: list[_SessionTarget] = []
        for index in range(max(cls._target_count_for_intent(intent), len(series_results))):
            resolved = series_results[index] if index < len(series_results) else None
            series_id = resolved.series.series_id if resolved is not None else None
            search_text = resolved.series.title if resolved is not None else None
            indicator = resolved.series.title if resolved is not None else None

            if index < len(base_targets):
                if base_targets[index].series_id:
                    series_id = base_targets[index].series_id
                if base_targets[index].search_text:
                    search_text = base_targets[index].search_text
                if base_targets[index].indicator:
                    indicator = base_targets[index].indicator

            if series_id or search_text or indicator:
                targets.append(
                    _SessionTarget(
                        series_id=series_id,
                        search_text=search_text,
                        indicator=indicator,
                    )
                )
        return targets

    @staticmethod
    def _build_parser_context(session_context: QuerySession | None) -> dict[str, object] | None:
        if session_context is None or session_context.last_response is None:
            return None

        previous_response = session_context.last_response
        previous_intent = (
            previous_response.query_response.intent
            if previous_response.query_response is not None
            else previous_response.intent
        )
        resolved_series = []
        if previous_response.query_response is not None:
            resolved_series = [
                {
                    "series_id": item.series.series_id,
                    "title": item.series.title,
                    "geography": item.series.geography,
                }
                for item in previous_response.query_response.analysis.series_results
            ]

        return {
            "previous_query": session_context.last_query,
            "previous_status": previous_response.status.value,
            "previous_intent": previous_intent.model_dump(mode="json"),
            "resolved_series": resolved_series,
            "clarification_candidates": [
                {
                    "series_id": candidate.series_id,
                    "title": candidate.title,
                }
                for candidate in previous_response.candidate_series
            ],
        }

    def _parse_intent(self, query: str, session_context: QuerySession | None) -> QueryIntent:
        parser_context = self._build_parser_context(session_context)
        parse_with_context = getattr(self.parser, "parse_with_context", None)
        if parser_context and callable(parse_with_context):
            return parse_with_context(query, parser_context)
        return self.parser.parse(query)

    @classmethod
    def _query_contains_any(cls, query: str, phrases: tuple[str, ...] | set[str]) -> bool:
        lowered = query.lower()
        return any(phrase in lowered for phrase in phrases)

    @classmethod
    def _query_mentions_transform(cls, query: str) -> bool:
        return cls._query_contains_any(query, cls._TRANSFORM_TERMS)

    @classmethod
    def _query_mentions_latest_reset(cls, query: str) -> bool:
        return cls._query_contains_any(query, cls._LATEST_RESET_TERMS)

    @classmethod
    def _intent_has_subject(cls, intent: QueryIntent) -> bool:
        return bool(
            intent.series_id
            or intent.search_text
            or intent.indicators
            or intent.geographies
            or any(intent.series_ids)
            or any(intent.search_texts)
        )

    @classmethod
    def _is_follow_up_query(cls, query: str, intent: QueryIntent, session_context: QuerySession | None) -> bool:
        if session_context is None or session_context.last_response is None:
            return False

        tokens = cls._tokenize(query)
        token_set = set(tokens)
        if token_set & cls._FOLLOW_UP_TOKENS:
            return True
        if tokens and tokens[0] in cls._FOLLOW_UP_LEADING_TOKENS and len(tokens) <= 8:
            return True
        if session_context.last_response.status == RoutedQueryStatus.NEEDS_CLARIFICATION and len(tokens) <= 8:
            return True
        if not cls._intent_has_subject(intent) and len(tokens) <= 8:
            return True
        return False

    @classmethod
    def _is_comparison_follow_up(cls, query: str, intent: QueryIntent) -> bool:
        return cls._query_contains_any(query, cls._COMPARISON_TERMS) and (
            len(cls._extract_targets_from_intent(intent)) < 2 or " it " in f" {query.lower()} "
        )

    @classmethod
    def _is_relationship_query(cls, query: str) -> bool:
        return cls._query_contains_any(query, cls._RELATIONSHIP_TERMS)

    @classmethod
    def _is_ranking_follow_up(cls, query: str, current: QueryIntent, previous: QueryIntent) -> bool:
        if current.task_type == TaskType.CROSS_SECTION:
            return previous.task_type == TaskType.CROSS_SECTION
        query_text = query.lower()
        return (
            previous.task_type == TaskType.CROSS_SECTION
            and any(term in query_text for term in ("rank", "top", "bottom", "highest", "lowest"))
        )

    @classmethod
    def _apply_temporal_follow_up_overrides(
        cls,
        merged: QueryIntent,
        current: QueryIntent,
        *,
        query: str,
    ) -> QueryIntent:
        if current.start_date is not None:
            merged.start_date = current.start_date
        if current.end_date is not None:
            merged.end_date = current.end_date
        elif cls._query_mentions_latest_reset(query):
            merged.end_date = None
        if current.observation_date is not None:
            merged.observation_date = current.observation_date
        elif cls._query_mentions_latest_reset(query):
            merged.observation_date = None
        if current.frequency:
            merged.frequency = current.frequency
        return merged

    @classmethod
    def _apply_transform_follow_up_overrides(
        cls,
        merged: QueryIntent,
        current: QueryIntent,
        *,
        query: str,
    ) -> QueryIntent:
        if cls._query_mentions_transform(query) or current.transform != TransformType.LEVEL or current.transform_window is not None:
            merged.transform = current.transform
            merged.transform_window = current.transform_window
            merged.normalization = current.normalization
        return merged

    @staticmethod
    def _merge_parser_notes(
        previous: QueryIntent,
        current: QueryIntent,
        *,
        previous_query: str | None,
    ) -> list[str]:
        merged_notes: list[str] = []
        for note in [*previous.parser_notes, *current.parser_notes]:
            if note and note not in merged_notes:
                merged_notes.append(note)
        if previous_query:
            merged_notes.append(f"Applied follow-up session context from prior query: {previous_query}")
        return merged_notes

    @classmethod
    def _overlay_single_subject_fields(cls, merged: QueryIntent, current: QueryIntent) -> QueryIntent:
        if current.series_id:
            merged.series_id = current.series_id
        if current.search_text:
            merged.search_text = current.search_text
        if current.indicators:
            merged.indicators = current.indicators
        if current.geographies:
            merged.geographies = current.geographies
        return merged

    @classmethod
    def _overlay_cross_section_fields(cls, merged: QueryIntent, current: QueryIntent, *, query: str) -> QueryIntent:
        merged.task_type = TaskType.CROSS_SECTION
        merged.comparison_mode = ComparisonMode.CROSS_SECTION
        if current.cross_section_scope is not None:
            merged.cross_section_scope = current.cross_section_scope
        if current.rank_limit is not None:
            merged.rank_limit = current.rank_limit
        query_text = query.lower()
        if any(term in query_text for term in cls._ASCENDING_TERMS):
            merged.sort_descending = False
        elif any(term in query_text for term in cls._DESCENDING_TERMS):
            merged.sort_descending = True
        return cls._overlay_single_subject_fields(merged, current)

    @classmethod
    def _build_comparison_follow_up(
        cls,
        previous: QueryIntent,
        current: QueryIntent,
        *,
        query: str,
        previous_targets: list[_SessionTarget],
        current_targets: list[_SessionTarget],
    ) -> QueryIntent:
        if len(current_targets) >= 2:
            merged = current.model_copy(deep=True)
            if merged.start_date is None:
                merged.start_date = previous.start_date
            if merged.end_date is None and not cls._query_mentions_latest_reset(query):
                merged.end_date = previous.end_date
            if not merged.frequency:
                merged.frequency = previous.frequency
            return merged

        if not previous_targets or not current_targets:
            return current

        new_target = current_targets[0]
        reference_target = previous_targets[0]
        merged = previous.model_copy(deep=True)
        merged.task_type = (
            TaskType.RELATIONSHIP_ANALYSIS
            if cls._is_relationship_query(query) or current.task_type == TaskType.RELATIONSHIP_ANALYSIS
            else TaskType.MULTI_SERIES_COMPARISON
        )
        merged.comparison_mode = (
            ComparisonMode.RELATIONSHIP
            if merged.task_type == TaskType.RELATIONSHIP_ANALYSIS
            else ComparisonMode.MULTI_SERIES
        )
        merged.series_id = None
        merged.search_text = None
        merged.cross_section_scope = None
        merged.rank_limit = None
        merged.series_ids = [reference_target.series_id, new_target.series_id]
        merged.search_texts = [
            reference_target.search_text or reference_target.indicator or reference_target.series_id or "series 1",
            new_target.search_text or new_target.indicator or new_target.series_id or "series 2",
        ]
        merged.indicators = [
            reference_target.indicator or reference_target.search_text or reference_target.series_id or "series 1",
            new_target.indicator or new_target.search_text or new_target.series_id or "series 2",
        ]
        return merged

    def _merge_follow_up_intent(
        self,
        query: str,
        current: QueryIntent,
        session_context: QuerySession | None,
    ) -> QueryIntent:
        previous = self._session_intent(session_context)
        if previous is None or not self._is_follow_up_query(query, current, session_context):
            return current

        previous_targets = self._resolved_session_targets(session_context)
        current_targets = self._extract_targets_from_intent(current)

        if self._is_comparison_follow_up(query, current):
            merged = self._build_comparison_follow_up(
                previous,
                current,
                query=query,
                previous_targets=previous_targets,
                current_targets=current_targets,
            )
        elif self._is_ranking_follow_up(query, current, previous):
            merged = self._overlay_cross_section_fields(previous.model_copy(deep=True), current, query=query)
        else:
            merged = previous.model_copy(deep=True)
            if current.task_type == TaskType.CROSS_SECTION:
                merged = self._overlay_cross_section_fields(merged, current, query=query)
            elif current.task_type in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS) and current_targets:
                merged.task_type = current.task_type
                merged.comparison_mode = current.comparison_mode
                if current.search_texts:
                    merged.search_texts = current.search_texts
                if current.series_ids:
                    merged.series_ids = current.series_ids
                if current.indicators:
                    merged.indicators = current.indicators
            else:
                if current.task_type != previous.task_type and self._intent_has_subject(current):
                    merged.task_type = current.task_type
                    merged.comparison_mode = current.comparison_mode
                merged = self._overlay_single_subject_fields(merged, current)

        merged = self._apply_temporal_follow_up_overrides(merged, current, query=query)
        merged = self._apply_transform_follow_up_overrides(merged, current, query=query)
        if current.units_preference:
            merged.units_preference = current.units_preference
        if current.transform_window is not None:
            merged.transform_window = current.transform_window
        if current.geographies:
            merged.geographies = current.geographies
        merged.original_query = query
        merged.clarification_needed = current.clarification_needed
        merged.clarification_question = current.clarification_question
        merged.clarification_target_index = current.clarification_target_index
        merged.parser_notes = self._merge_parser_notes(
            previous,
            current,
            previous_query=session_context.last_query if session_context is not None else None,
        )
        return merged

    def ask(
        self,
        query: str,
        *,
        selected_series_id: str | None = None,
        selected_series_ids: list[str | None] | None = None,
        session_context: QuerySession | None = None,
    ) -> RoutedQueryResponse:
        effective_selected_series_ids = selected_series_ids
        if effective_selected_series_ids is None and selected_series_id is not None:
            effective_selected_series_ids = [selected_series_id]

        intent = self._parse_intent(query, session_context)
        intent = self._merge_follow_up_intent(query, intent, session_context)
        intent = self._apply_selected_series(intent, effective_selected_series_ids)

        if intent.clarification_needed:
            candidate_series = self._build_clarification_candidates(intent)
            return RoutedQueryResponse(
                status=RoutedQueryStatus.NEEDS_CLARIFICATION,
                intent=intent,
                answer_text=self._clarification_answer_text(intent, candidate_series=candidate_series),
                candidate_series=candidate_series,
            )

        if intent.task_type == TaskType.STATE_GDP_COMPARISON:
            if len(intent.geographies) != 2:
                return RoutedQueryResponse(
                    status=RoutedQueryStatus.NEEDS_CLARIFICATION,
                    intent=intent,
                    answer_text="I need exactly two US states to run the GDP comparison.",
                )

            query_response = self.state_gdp_service.compare(
                state1=intent.geographies[0].name,
                state2=intent.geographies[1].name,
                start_date=intent.start_date or self._default_start_date(),
                end_date=intent.end_date,
                normalize=intent.normalization,
            )
            return RoutedQueryResponse(
                status=RoutedQueryStatus.COMPLETED,
                intent=query_response.intent,
                answer_text=query_response.answer_text,
                query_response=query_response,
            )

        if intent.task_type == TaskType.SINGLE_SERIES_LOOKUP:
            query_response = self.single_series_service.lookup(intent)
            return RoutedQueryResponse(
                status=RoutedQueryStatus.COMPLETED,
                intent=query_response.intent,
                answer_text=query_response.answer_text,
                query_response=query_response,
            )

        if intent.task_type == TaskType.CROSS_SECTION:
            query_response = self.cross_section_service.analyze(intent)
            return RoutedQueryResponse(
                status=RoutedQueryStatus.COMPLETED,
                intent=query_response.intent,
                answer_text=query_response.answer_text,
                query_response=query_response,
            )

        if intent.task_type in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS):
            query_response = self.relationship_service.analyze(intent)
            return RoutedQueryResponse(
                status=RoutedQueryStatus.COMPLETED,
                intent=query_response.intent,
                answer_text=query_response.answer_text,
                query_response=query_response,
            )

        return RoutedQueryResponse(
            status=RoutedQueryStatus.UNSUPPORTED,
            intent=intent,
            answer_text=(
                "The parser understood the request, but there is no deterministic execution path for it yet. "
                "Right now the live implementation supports state GDP comparisons, point-in-time cross sections, "
                "single-series lookups, and pairwise non-state relationship analysis."
            ),
        )
