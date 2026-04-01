from __future__ import annotations

import re

from fred_query.schemas.intent import QueryIntent, TaskType
from fred_query.schemas.resolved_series import SeriesSearchMatch
from fred_query.services.fred_client import FREDClient


class ClarificationResolver:
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

    def __init__(self, fred_client: FREDClient) -> None:
        self.fred_client = fred_client

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

    def clarification_search_text(self, intent: QueryIntent) -> str | None:
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
            for term in (
                "core",
                "trimmed",
                "breakeven",
                "deflator",
                "producer",
                "annualized",
                "year over year",
            )
        )

    @classmethod
    def _candidate_has_any(cls, candidate: SeriesSearchMatch, terms: tuple[str, ...]) -> bool:
        text = cls._candidate_text(candidate)
        return any(term in text for term in terms)

    @classmethod
    def _is_base_price_index(cls, candidate: SeriesSearchMatch) -> bool:
        text = cls._candidate_text(candidate)
        if not (
            "consumer price index" in text
            or "personal consumption expenditures" in text
            or re.search(r"\bcpi\b", text)
            or re.search(r"\bpce\b", text)
        ):
            return False
        return "index" in text and not cls._has_specialized_inflation_variant(candidate)

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

    def build_candidates(self, intent: QueryIntent) -> list[SeriesSearchMatch]:
        search_text = self.clarification_search_text(intent)
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
            return self.annotate_candidates(merged_candidates[:4], intent=intent)

        fallback_candidates = prioritized + [
            candidate
            for candidate in self._dedupe_ranked_candidates(ranked)
            if self._candidate_title_key(candidate) not in prioritized_keys
        ]
        if fallback_candidates:
            return self.annotate_candidates(fallback_candidates[:4], intent=intent)

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

    def annotate_candidates(
        self,
        candidates: list[SeriesSearchMatch],
        *,
        intent: QueryIntent,
    ) -> list[SeriesSearchMatch]:
        search_text = self.clarification_search_text(intent)
        return [
            candidate.model_copy(
                update={
                    "selection_label": self._selection_label_for_candidate(candidate),
                    "selection_hint": self._selection_hint_for_candidate(candidate, search_text=search_text),
                    "selection_badges": self._selection_badges_for_candidate(candidate),
                }
            )
            for candidate in candidates
        ]

    @staticmethod
    def answer_text(
        intent: QueryIntent,
        *,
        candidate_series: list[SeriesSearchMatch],
    ) -> str:
        question = intent.clarification_question or "I need one clarification before I can query FRED safely."
        if candidate_series:
            return f"{question} Pick one of the series below to continue."
        return question
