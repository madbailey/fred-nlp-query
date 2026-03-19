from __future__ import annotations

from datetime import date, timedelta
import re

from fred_query.schemas.analysis import RoutedQueryResponse, RoutedQueryStatus
from fred_query.schemas.resolved_series import SeriesSearchMatch
from fred_query.schemas.intent import TaskType
from fred_query.services.comparison_service import StateGDPComparisonService
from fred_query.services.fred_client import FREDClient
from fred_query.services.openai_parser_service import OpenAIIntentParser
from fred_query.services.relationship_service import RelationshipAnalysisService
from fred_query.services.single_series_service import SingleSeriesLookupService


class NaturalLanguageQueryService:
    """Route a natural-language query into deterministic execution."""

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

    def __init__(
        self,
        *,
        parser: OpenAIIntentParser,
        fred_client: FREDClient,
        state_gdp_service: StateGDPComparisonService | None = None,
        single_series_service: SingleSeriesLookupService | None = None,
        relationship_service: RelationshipAnalysisService | None = None,
    ) -> None:
        self.parser = parser
        self.fred_client = fred_client
        self.state_gdp_service = state_gdp_service or StateGDPComparisonService(fred_client)
        self.single_series_service = single_series_service or SingleSeriesLookupService(fred_client)
        self.relationship_service = relationship_service or RelationshipAnalysisService(fred_client)

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

    def _clarification_search_text(self, intent) -> str | None:
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

        return score

    def _build_clarification_candidates(self, intent) -> list[SeriesSearchMatch]:
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
        filtered = [candidate for score, candidate in ranked if score >= minimum_score]
        if filtered:
            return filtered[:4]

        if example_searches:
            return []

        return [candidate for _, candidate in ranked[:4]]

    @staticmethod
    def _apply_selected_series(intent, selected_series_ids: list[str | None] | None):
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

    def ask(
        self,
        query: str,
        *,
        selected_series_id: str | None = None,
        selected_series_ids: list[str | None] | None = None,
    ) -> RoutedQueryResponse:
        effective_selected_series_ids = selected_series_ids
        if effective_selected_series_ids is None and selected_series_id is not None:
            effective_selected_series_ids = [selected_series_id]
        intent = self._apply_selected_series(
            self.parser.parse(query),
            effective_selected_series_ids,
        )

        if intent.clarification_needed:
            return RoutedQueryResponse(
                status=RoutedQueryStatus.NEEDS_CLARIFICATION,
                intent=intent,
                answer_text=intent.clarification_question or "I need one clarification before I can query FRED safely.",
                candidate_series=self._build_clarification_candidates(intent),
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
                intent=intent,
                answer_text=query_response.answer_text,
                query_response=query_response,
            )

        if intent.task_type == TaskType.SINGLE_SERIES_LOOKUP:
            query_response = self.single_series_service.lookup(intent)
            return RoutedQueryResponse(
                status=RoutedQueryStatus.COMPLETED,
                intent=intent,
                answer_text=query_response.answer_text,
                query_response=query_response,
            )

        if intent.task_type in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS):
            query_response = self.relationship_service.analyze(intent)
            return RoutedQueryResponse(
                status=RoutedQueryStatus.COMPLETED,
                intent=intent,
                answer_text=query_response.answer_text,
                query_response=query_response,
            )

        return RoutedQueryResponse(
            status=RoutedQueryStatus.UNSUPPORTED,
            intent=intent,
            answer_text=(
                "The parser understood the request, but there is no deterministic execution path for it yet. "
                "Right now the live implementation supports state GDP comparisons, single-series lookups, and "
                "pairwise non-state relationship analysis."
            ),
        )
