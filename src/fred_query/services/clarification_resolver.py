from __future__ import annotations

import re

from fred_query.schemas.intent import QueryIntent, TaskType
from fred_query.schemas.resolved_series import ClarificationBadge, ClarificationOption, SeriesSearchMatch
from fred_query.services.fred_client import FREDClient
from fred_query.services.series_match_scorer import (
    CandidateFeatures as _ClarificationCandidateFeatures,
    MatchScoreContext as _ClarificationContext,
    build_match_score_context,
    candidate_is_seasonally_adjusted,
    candidate_text,
    extract_candidate_features,
    extract_candidate_features_from_text,
    extract_clarification_examples,
    has_specialized_inflation_variant,
    is_base_price_index,
    is_plain_inflation_request,
    normalized_text,
    score_candidate,
)


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
    def __init__(self, fred_client: FREDClient) -> None:
        self.fred_client = fred_client

    @classmethod
    def _extract_clarification_examples(cls, question: str | None) -> list[str]:
        return extract_clarification_examples(question)

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
        return build_match_score_context(intent)

    @staticmethod
    def _extract_candidate_features_from_text(text: str) -> _ClarificationCandidateFeatures:
        return extract_candidate_features_from_text(text)

    @classmethod
    def _extract_candidate_features(cls, candidate: SeriesSearchMatch) -> _ClarificationCandidateFeatures:
        return extract_candidate_features(candidate)

    @staticmethod
    def _candidate_is_seasonally_adjusted(candidate: SeriesSearchMatch) -> bool | None:
        return candidate_is_seasonally_adjusted(candidate)

    @classmethod
    def _score_candidate(
        cls,
        candidate: SeriesSearchMatch,
        *,
        context: _ClarificationContext,
    ) -> float:
        return score_candidate(candidate, context=context)

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
        return normalized_text(value)

    @classmethod
    def _is_plain_inflation_request(cls, search_variants: list[str]) -> bool:
        return is_plain_inflation_request(search_variants)

    @classmethod
    def _candidate_has_any(cls, candidate: SeriesSearchMatch, terms: tuple[str, ...]) -> bool:
        text = cls._candidate_text(candidate)
        return any(term in text for term in terms)

    @classmethod
    def _is_base_price_index(cls, candidate: SeriesSearchMatch) -> bool:
        return is_base_price_index(candidate)

    @classmethod
    def _has_specialized_inflation_variant(cls, candidate: SeriesSearchMatch) -> bool:
        return has_specialized_inflation_variant(candidate)

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
        return candidate_text(candidate)

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
