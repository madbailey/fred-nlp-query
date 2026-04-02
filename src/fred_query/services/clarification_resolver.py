from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

from fred_query.schemas.intent import QueryIntent, TaskType
from fred_query.schemas.resolved_series import ClarificationBadge, ClarificationOption, SeriesSearchMatch
from fred_query.services.fred_client import FREDClient


@dataclass(frozen=True)
class _ClarificationQueryFeatures:
    normalized_text: str
    wants_real: bool
    wants_nominal: bool
    wants_growth_rate: bool
    wants_per_capita: bool
    wants_market_based: bool
    wants_seasonally_adjusted: bool | None


@dataclass(frozen=True)
class _ClarificationCandidateFeatures:
    normalized_text: str
    has_real: bool
    has_nominal: bool
    has_growth_rate: bool
    has_index_level: bool
    has_per_capita: bool
    has_market_based_signal: bool
    has_instrument_terms: bool
    has_core: bool
    has_pce: bool
    has_cpi: bool
    has_trimmed_mean: bool
    has_ppi: bool
    has_deflator: bool


@dataclass(frozen=True)
class _ClarificationContext:
    search_text: str | None
    example_searches: tuple[str, ...]
    search_variants: tuple[str, ...]
    anchor_terms: tuple[str, ...]
    query_features: _ClarificationQueryFeatures


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
    _GROWTH_RATE_TERMS = (
        "% chg",
        "annual rate",
        "annualized",
        "growth rate",
        "percent change",
        "rate of change",
        "year over year",
        "yr. ago",
        "yoy",
    )
    _REAL_TERMS = (
        "constant dollar",
        "constant dollars",
        "inflation-adjusted",
    )
    _NOMINAL_TERMS = (
        "current dollar",
        "current dollars",
        "current-dollar",
        "nominal",
    )
    _PER_CAPITA_TERMS = (
        "per capita",
        "per-capita",
    )
    _MARKET_BASED_TERMS = (
        "breakeven",
        "inflation compensation",
        "inflation-indexed",
        "market-based",
    )

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

    @staticmethod
    def clarification_search_text(intent: QueryIntent) -> str | None:
        search_text = intent.search_text
        if (
            intent.task_type in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS)
            and intent.clarification_target_index is not None
            and intent.clarification_target_index < len(intent.search_texts)
        ):
            search_text = intent.search_texts[intent.clarification_target_index]
        return search_text

    @classmethod
    def _build_context(cls, intent: QueryIntent) -> _ClarificationContext | None:
        search_text = cls.clarification_search_text(intent)
        if not search_text:
            return None

        example_searches = cls._extract_clarification_examples(intent.clarification_question)
        search_variants: list[str] = []
        for value in [*example_searches, search_text]:
            normalized = value.strip()
            if normalized and normalized not in search_variants:
                search_variants.append(normalized)

        context_texts = cls._context_texts_for_intent(
            intent,
            search_text=search_text,
            example_searches=example_searches,
        )
        anchor_terms = cls._significant_terms(
            context_texts
        )
        query_text = " ".join(
            part
            for part in context_texts
            if part
        )
        return _ClarificationContext(
            search_text=search_text,
            example_searches=tuple(example_searches),
            search_variants=tuple(search_variants),
            anchor_terms=tuple(anchor_terms),
            query_features=cls._extract_query_features(query_text),
        )

    @classmethod
    def _text_has_any(cls, text: str, terms: tuple[str, ...]) -> bool:
        return any(term in text for term in terms)

    @classmethod
    def _context_texts_for_intent(
        cls,
        intent: QueryIntent,
        *,
        search_text: str,
        example_searches: list[str],
    ) -> list[str]:
        texts = [
            intent.clarification_question or "",
            search_text,
            *example_searches,
        ]
        if intent.task_type not in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS):
            texts.insert(0, intent.original_query or "")
        return texts

    @classmethod
    def _extract_query_features(cls, text: str) -> _ClarificationQueryFeatures:
        normalized = cls._normalized_text(text)
        wants_seasonally_adjusted: bool | None = None
        if "not seasonally adjusted" in normalized:
            wants_seasonally_adjusted = False
        elif "seasonally adjusted" in normalized:
            wants_seasonally_adjusted = True

        return _ClarificationQueryFeatures(
            normalized_text=normalized,
            wants_real=cls._has_real_signal(normalized),
            wants_nominal=cls._has_nominal_signal(normalized),
            wants_growth_rate=cls._text_has_any(normalized, cls._GROWTH_RATE_TERMS),
            wants_per_capita=cls._text_has_any(normalized, cls._PER_CAPITA_TERMS),
            wants_market_based=cls._text_has_any(normalized, cls._MARKET_BASED_TERMS)
            or any(term in normalized for term in cls._INSTRUMENT_TERMS),
            wants_seasonally_adjusted=wants_seasonally_adjusted,
        )

    @staticmethod
    @lru_cache(maxsize=1024)
    def _extract_candidate_features_from_text(text: str) -> _ClarificationCandidateFeatures:
        has_growth_rate = ClarificationResolver._text_has_any(text, ClarificationResolver._GROWTH_RATE_TERMS)
        has_real = ClarificationResolver._has_real_signal(text)
        return _ClarificationCandidateFeatures(
            normalized_text=text,
            has_real=has_real,
            has_nominal=ClarificationResolver._has_nominal_signal(text, has_real=has_real),
            has_growth_rate=has_growth_rate,
            has_index_level="index" in text and not has_growth_rate,
            has_per_capita=ClarificationResolver._text_has_any(text, ClarificationResolver._PER_CAPITA_TERMS),
            has_market_based_signal=ClarificationResolver._text_has_any(text, ClarificationResolver._MARKET_BASED_TERMS),
            has_instrument_terms=any(term in text for term in ClarificationResolver._INSTRUMENT_TERMS),
            has_core=(
                "core" in text
                or "less food and energy" in text
                or "excluding food and energy" in text
            ),
            has_pce=(
                "personal consumption expenditures" in text
                or re.search(r"\bpce\b", text) is not None
            ),
            has_cpi="consumer price index" in text or re.search(r"\bcpi\b", text) is not None,
            has_trimmed_mean="trimmed mean" in text,
            has_ppi="producer price" in text or re.search(r"\bppi\b", text) is not None,
            has_deflator="deflator" in text,
        )

    @classmethod
    def _extract_candidate_features(cls, candidate: SeriesSearchMatch) -> _ClarificationCandidateFeatures:
        text = cls._candidate_text(candidate)
        return cls._extract_candidate_features_from_text(text)

    @classmethod
    def _has_real_signal(cls, text: str) -> bool:
        if cls._text_has_any(text, cls._REAL_TERMS):
            return True
        if re.search(r"\breal\b", text) is not None:
            return True
        return re.search(r"\bchained\b.+\bdollar", text) is not None

    @classmethod
    def _has_nominal_signal(cls, text: str, *, has_real: bool | None = None) -> bool:
        if cls._text_has_any(text, cls._NOMINAL_TERMS):
            return True
        if has_real is None:
            has_real = cls._has_real_signal(text)
        if has_real:
            return False
        return re.search(r"\bdollars?\b", text) is not None

    @staticmethod
    def _candidate_is_seasonally_adjusted(candidate: SeriesSearchMatch) -> bool | None:
        adjustment = (candidate.seasonal_adjustment or "").strip().lower()
        if not adjustment:
            return None
        if "not seasonally adjusted" in adjustment or adjustment == "nsa":
            return False
        if "seasonally adjusted" in adjustment or adjustment in {"sa", "saar"}:
            return True
        return None

    @classmethod
    def _generic_score_adjustment(
        cls,
        candidate: SeriesSearchMatch,
        candidate_features: _ClarificationCandidateFeatures,
        *,
        context: _ClarificationContext,
    ) -> float:
        score = 0.0
        query_features = context.query_features

        if query_features.wants_real:
            if candidate_features.has_real:
                score += 2.0
            elif candidate_features.has_nominal:
                score -= 1.5

        if query_features.wants_nominal:
            if candidate_features.has_nominal:
                score += 2.0
            elif candidate_features.has_real:
                score -= 1.5

        if query_features.wants_growth_rate:
            if candidate_features.has_growth_rate:
                score += 1.5
            elif candidate_features.has_index_level:
                score -= 0.5

        if query_features.wants_per_capita:
            if candidate_features.has_per_capita:
                score += 1.5
            else:
                score -= 0.5

        if query_features.wants_market_based:
            if candidate_features.has_market_based_signal or candidate_features.has_instrument_terms:
                score += 1.5
        elif candidate_features.has_instrument_terms:
            score -= 1.5

        seasonally_adjusted = cls._candidate_is_seasonally_adjusted(candidate)
        if query_features.wants_seasonally_adjusted is True:
            if seasonally_adjusted is True:
                score += 1.0
            elif seasonally_adjusted is False:
                score -= 0.5
        elif query_features.wants_seasonally_adjusted is False:
            if seasonally_adjusted is False:
                score += 1.0
            elif seasonally_adjusted is True:
                score -= 0.5

        return score

    @classmethod
    def _inflation_profile_score_adjustment(
        cls,
        candidate: SeriesSearchMatch,
        *,
        context: _ClarificationContext,
        candidate_features: _ClarificationCandidateFeatures,
    ) -> float:
        if not cls._is_plain_inflation_request(list(context.search_variants)):
            return 0.0

        score = 0.0
        if cls._is_base_price_index(candidate):
            score += 2.5
        if cls._has_specialized_inflation_variant(candidate):
            score -= 2.0
        if candidate_features.has_instrument_terms and not context.query_features.wants_market_based:
            score -= 0.5
        return score

    @classmethod
    def _score_candidate(
        cls,
        candidate: SeriesSearchMatch,
        *,
        context: _ClarificationContext,
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

        candidate_features = cls._extract_candidate_features(candidate)
        score = 0.0
        title_matches = 0
        for term in context.anchor_terms:
            if term in title_text:
                score += 3.0
                title_matches += 1
            elif term in full_text:
                score += 1.0

        for phrase in context.search_variants:
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

        if title_matches == 0:
            score -= 2.0

        score += cls._generic_score_adjustment(candidate, candidate_features, context=context)
        score += cls._inflation_profile_score_adjustment(
            candidate,
            context=context,
            candidate_features=candidate_features,
        )
        return score

    @classmethod
    def _candidate_title_key(cls, candidate: SeriesSearchMatch) -> str:
        title_key = re.sub(r"\s+", " ", candidate.title.strip().lower())
        features = cls._extract_candidate_features(candidate)
        seasonality = cls._candidate_is_seasonally_adjusted(candidate)
        semantic_parts = [
            "growth" if features.has_growth_rate else "level",
            "real" if features.has_real else "",
            "nominal" if features.has_nominal else "",
            "per_capita" if features.has_per_capita else "",
            "market" if features.has_market_based_signal or features.has_instrument_terms else "",
            "sa" if seasonality is True else "",
            "nsa" if seasonality is False else "",
        ]
        semantic_key = "|".join(part for part in semantic_parts if part)
        return f"{title_key}|{semantic_key}"

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
        context = self._build_context(intent)
        if context is None:
            return []

        scored_candidates: dict[str, tuple[float, SeriesSearchMatch]] = {}
        variant_rankings: dict[str, list[tuple[float, SeriesSearchMatch]]] = {}
        for variant_index, variant in enumerate(context.search_variants):
            try:
                matches = self.fred_client.search_series(variant, limit=6)
            except Exception:
                continue

            for rank, candidate in enumerate(matches):
                score = self._score_candidate(
                    candidate,
                    context=context,
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

        minimum_score = 5.0 if context.example_searches else 2.0
        filtered = self._dedupe_candidates([candidate for score, candidate in ranked if score >= minimum_score])
        prioritized: list[SeriesSearchMatch] = []
        prioritized_keys: set[str] = set()
        for example in context.example_searches:
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
    def _inflation_selection_hint_for_candidate(
        cls,
        candidate_features: _ClarificationCandidateFeatures,
    ) -> str | None:
        if candidate_features.has_trimmed_mean and candidate_features.has_pce:
            return "Pick this if you want trimmed-mean PCE, a smoother Dallas Fed trend measure rather than the standard headline PCE series."
        if candidate_features.has_core and candidate_features.has_pce:
            return "Pick this if you want core PCE inflation, which strips out food and energy and is closely watched by the Fed."
        if candidate_features.has_core and candidate_features.has_cpi:
            return "Pick this if you want core CPI inflation, which strips out food and energy from the consumer price index."
        if candidate_features.has_pce and candidate_features.has_growth_rate:
            return "Pick this if you want PCE inflation already expressed as a rate of change rather than as the raw price index."
        if candidate_features.has_cpi and candidate_features.has_growth_rate:
            return "Pick this if you want CPI already expressed as a rate of change rather than as the raw price index."
        if candidate_features.has_pce:
            return "Pick this if you want PCE inflation, the consumption-based price measure the Fed often references."
        if candidate_features.has_cpi:
            return "Pick this if you want CPI, the broad consumer inflation measure most people mean by 'inflation'."
        if candidate_features.has_market_based_signal:
            return "Pick this if you want a market-implied inflation expectation from Treasury pricing, not a realized inflation index."
        if candidate_features.has_ppi:
            return "Pick this if you want producer-price inflation rather than consumer inflation."
        if candidate_features.has_deflator:
            return "Pick this if you want a deflator-style price measure rather than a headline consumer index."
        if candidate_features.has_core:
            return "Pick this if you want a core inflation measure that strips out volatile categories."
        return None

    @classmethod
    def _generic_selection_hint_for_candidate(
        cls,
        candidate: SeriesSearchMatch,
        *,
        search_text: str | None,
        candidate_features: _ClarificationCandidateFeatures,
    ) -> str:
        descriptors: list[str] = []
        if candidate_features.has_real:
            descriptors.append("inflation-adjusted")
        elif candidate_features.has_nominal:
            descriptors.append("nominal/current-dollar")
        if candidate_features.has_per_capita:
            descriptors.append("per-capita")
        if candidate_features.has_growth_rate:
            descriptors.append("growth-rate")
        elif candidate_features.has_index_level:
            descriptors.append("index-level")

        if descriptors:
            descriptor_text = ", ".join(descriptors)
            return f"Pick this if you want the {descriptor_text} version of {search_text or 'the requested measure'}."

        if candidate.frequency and candidate.units:
            return (
                f"Pick this if you want {candidate.frequency.lower()} data reported in {candidate.units.lower()} "
                f"for {search_text or 'the requested measure'}."
            )
        if candidate.frequency:
            return f"Pick this if you want {candidate.frequency.lower()} data for {search_text or 'the requested measure'}."
        return f'Pick this if you want the series titled "{candidate.title}".'

    @classmethod
    def _selection_hint_for_candidate(
        cls,
        candidate: SeriesSearchMatch,
        *,
        search_text: str | None,
    ) -> str:
        candidate_features = cls._extract_candidate_features(candidate)
        inflation_hint = cls._inflation_selection_hint_for_candidate(candidate_features)
        if inflation_hint is not None:
            return inflation_hint
        return cls._generic_selection_hint_for_candidate(
            candidate,
            search_text=search_text,
            candidate_features=candidate_features,
        )

    @classmethod
    def _selection_label_for_candidate(cls, candidate: SeriesSearchMatch) -> str | None:
        candidate_features = cls._extract_candidate_features(candidate)
        if candidate_features.has_trimmed_mean and candidate_features.has_pce:
            return "Trimmed Mean PCE"
        if candidate_features.has_core and candidate_features.has_pce:
            return "Core PCE"
        if candidate_features.has_core and candidate_features.has_cpi:
            return "Core CPI"
        if candidate_features.has_pce:
            return "Headline PCE"
        if candidate_features.has_cpi:
            return "Headline CPI"
        if candidate_features.has_market_based_signal:
            return "Market Inflation Expectations"
        if candidate_features.has_ppi:
            return "Producer Prices"
        if candidate_features.has_deflator:
            return "Price Deflator"
        if candidate_features.has_real and candidate_features.has_per_capita and candidate_features.has_growth_rate:
            return "Real Per Capita Growth Rate"
        if candidate_features.has_nominal and candidate_features.has_per_capita and candidate_features.has_growth_rate:
            return "Nominal Per Capita Growth Rate"
        if candidate_features.has_per_capita and candidate_features.has_growth_rate:
            return "Per Capita Growth Rate"
        if candidate_features.has_real and candidate_features.has_growth_rate:
            return "Real Growth Rate"
        if candidate_features.has_nominal and candidate_features.has_growth_rate:
            return "Nominal Growth Rate"
        if candidate_features.has_real and candidate_features.has_per_capita:
            return "Real Per Capita Series"
        if candidate_features.has_nominal and candidate_features.has_per_capita:
            return "Nominal Per Capita Series"
        if candidate_features.has_real:
            return "Real Series"
        if candidate_features.has_nominal:
            return "Nominal Series"
        if candidate_features.has_per_capita:
            return "Per Capita Series"
        if candidate_features.has_growth_rate:
            return "Growth Rate"
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

    @staticmethod
    def _clarification_badge_kind(label: str) -> str:
        lowered = label.lower()
        if lowered in {"daily", "weekly", "biweekly", "monthly", "quarterly", "semiannual", "annual"}:
            return "frequency"
        if lowered in {"index level", "percent", "yoy rate", "annualized rate", "6m annualized"}:
            return "units"
        return "metadata"

    def _annotated_candidate_update(
        self,
        candidate: SeriesSearchMatch,
        *,
        search_text: str | None,
    ) -> dict[str, object]:
        label = self._selection_label_for_candidate(candidate)
        hint = self._selection_hint_for_candidate(candidate, search_text=search_text)
        badges = self._selection_badges_for_candidate(candidate)
        return {
            "selection_label": label,
            "selection_hint": hint,
            "selection_badges": badges,
            "clarification_option": ClarificationOption(
                label=label or candidate.title,
                title=candidate.title,
                hint=hint,
                badges=[
                    ClarificationBadge(kind=self._clarification_badge_kind(badge), label=badge)
                    for badge in badges
                ],
            ),
        }

    def annotate_candidates(
        self,
        candidates: list[SeriesSearchMatch],
        *,
        intent: QueryIntent,
    ) -> list[SeriesSearchMatch]:
        context = self._build_context(intent)
        search_text = context.search_text if context is not None else self.clarification_search_text(intent)
        return [
            candidate.model_copy(
                update=self._annotated_candidate_update(candidate, search_text=search_text)
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
