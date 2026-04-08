from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

from fred_query.schemas.intent import QueryIntent, TaskType
from fred_query.schemas.resolved_series import SeriesSearchMatch


STOP_WORDS = {
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
INSTRUMENT_TERMS = {
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
GROWTH_RATE_TERMS = (
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
REAL_TERMS = (
    "constant dollar",
    "constant dollars",
    "inflation-adjusted",
)
NOMINAL_TERMS = (
    "current dollar",
    "current dollars",
    "current-dollar",
    "nominal",
)
PER_CAPITA_TERMS = (
    "per capita",
    "per-capita",
)
MARKET_BASED_TERMS = (
    "breakeven",
    "inflation compensation",
    "inflation-indexed",
    "market-based",
)
SCORE_WEIGHTS = {
    "query_wants_real_match": 2.0,
    "query_wants_real_penalty": 1.5,
    "query_wants_nominal_match": 2.0,
    "query_wants_nominal_penalty": 1.5,
    "query_wants_growth_match": 1.5,
    "query_wants_growth_penalty": 0.5,
    "query_wants_per_capita_match": 1.5,
    "query_wants_per_capita_penalty": 0.5,
    "query_wants_market_based_match": 1.5,
    "unexpected_instrument_penalty": 1.5,
    "seasonal_adjustment_match": 1.0,
    "seasonal_adjustment_penalty": 0.5,
    "inflation_base_index_bonus": 2.5,
    "inflation_specialized_penalty": 2.0,
    "inflation_unwanted_instrument_penalty": 0.5,
    "anchor_term_title_match": 3.0,
    "anchor_term_full_text_match": 1.0,
    "exact_phrase_match": 5.0,
    "partial_phrase_match": 3.5,
    "popularity_divisor": 25.0,
    "popularity_cap": 2.0,
    "no_title_match_penalty": 2.0,
}


@dataclass(frozen=True)
class QueryFeatures:
    normalized_text: str
    wants_real: bool
    wants_nominal: bool
    wants_growth_rate: bool
    wants_per_capita: bool
    wants_market_based: bool
    wants_seasonally_adjusted: bool | None


@dataclass(frozen=True)
class CandidateFeatures:
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
class MatchScoreContext:
    search_text: str | None
    example_searches: tuple[str, ...]
    search_variants: tuple[str, ...]
    anchor_terms: tuple[str, ...]
    query_features: QueryFeatures


def tokenize(text: str | None) -> list[str]:
    if not text:
        return []
    return re.findall(r"[A-Za-z0-9]+", text.lower())


def significant_terms(texts: list[str]) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for text in texts:
        for token in tokenize(text):
            if len(token) < 3 or token in STOP_WORDS:
                continue
            if token in seen:
                continue
            seen.add(token)
            terms.append(token)
    return terms


def extract_clarification_examples(question: str | None) -> list[str]:
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


def clarification_search_text(intent: QueryIntent) -> str | None:
    search_text = intent.search_text
    if (
        intent.task_type in (TaskType.MULTI_SERIES_COMPARISON, TaskType.RELATIONSHIP_ANALYSIS)
        and intent.clarification_target_index is not None
        and intent.clarification_target_index < len(intent.search_texts)
    ):
        search_text = intent.search_texts[intent.clarification_target_index]
    return search_text


def context_texts_for_intent(
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


def text_has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def normalized_text(value: str | None) -> str:
    return (value or "").strip().lower()


def has_real_signal(text: str) -> bool:
    if text_has_any(text, REAL_TERMS):
        return True
    if re.search(r"\breal\b", text) is not None:
        return True
    return re.search(r"\bchained\b.+\bdollar", text) is not None


def has_nominal_signal(text: str, *, has_real: bool | None = None) -> bool:
    if text_has_any(text, NOMINAL_TERMS):
        return True
    if has_real is None:
        has_real = has_real_signal(text)
    if has_real:
        return False
    return re.search(r"\bdollars?\b", text) is not None


def extract_query_features(text: str) -> QueryFeatures:
    normalized = normalized_text(text)
    wants_seasonally_adjusted: bool | None = None
    if "not seasonally adjusted" in normalized:
        wants_seasonally_adjusted = False
    elif "seasonally adjusted" in normalized:
        wants_seasonally_adjusted = True

    return QueryFeatures(
        normalized_text=normalized,
        wants_real=has_real_signal(normalized),
        wants_nominal=has_nominal_signal(normalized),
        wants_growth_rate=text_has_any(normalized, GROWTH_RATE_TERMS),
        wants_per_capita=text_has_any(normalized, PER_CAPITA_TERMS),
        wants_market_based=text_has_any(normalized, MARKET_BASED_TERMS)
        or any(term in normalized for term in INSTRUMENT_TERMS),
        wants_seasonally_adjusted=wants_seasonally_adjusted,
    )


@lru_cache(maxsize=1024)
def extract_candidate_features_from_text(text: str) -> CandidateFeatures:
    has_growth_rate = text_has_any(text, GROWTH_RATE_TERMS)
    has_real = has_real_signal(text)
    return CandidateFeatures(
        normalized_text=text,
        has_real=has_real,
        has_nominal=has_nominal_signal(text, has_real=has_real),
        has_growth_rate=has_growth_rate,
        has_index_level="index" in text and not has_growth_rate,
        has_per_capita=text_has_any(text, PER_CAPITA_TERMS),
        has_market_based_signal=text_has_any(text, MARKET_BASED_TERMS),
        has_instrument_terms=any(term in text for term in INSTRUMENT_TERMS),
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


def candidate_text(candidate: SeriesSearchMatch) -> str:
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


def extract_candidate_features(candidate: SeriesSearchMatch) -> CandidateFeatures:
    return extract_candidate_features_from_text(candidate_text(candidate))


def candidate_is_seasonally_adjusted(candidate: SeriesSearchMatch) -> bool | None:
    adjustment = (candidate.seasonal_adjustment or "").strip().lower()
    if not adjustment:
        return None
    if "not seasonally adjusted" in adjustment or adjustment == "nsa":
        return False
    if "seasonally adjusted" in adjustment or adjustment in {"sa", "saar"}:
        return True
    return None


def generic_score_adjustment(
    candidate: SeriesSearchMatch,
    candidate_features: CandidateFeatures,
    *,
    context: MatchScoreContext,
) -> float:
    score = 0.0
    query_features = context.query_features

    if query_features.wants_real:
        if candidate_features.has_real:
            score += SCORE_WEIGHTS["query_wants_real_match"]
        elif candidate_features.has_nominal:
            score -= SCORE_WEIGHTS["query_wants_real_penalty"]

    if query_features.wants_nominal:
        if candidate_features.has_nominal:
            score += SCORE_WEIGHTS["query_wants_nominal_match"]
        elif candidate_features.has_real:
            score -= SCORE_WEIGHTS["query_wants_nominal_penalty"]

    if query_features.wants_growth_rate:
        if candidate_features.has_growth_rate:
            score += SCORE_WEIGHTS["query_wants_growth_match"]
        elif candidate_features.has_index_level:
            score -= SCORE_WEIGHTS["query_wants_growth_penalty"]

    if query_features.wants_per_capita:
        if candidate_features.has_per_capita:
            score += SCORE_WEIGHTS["query_wants_per_capita_match"]
        else:
            score -= SCORE_WEIGHTS["query_wants_per_capita_penalty"]

    if query_features.wants_market_based:
        if candidate_features.has_market_based_signal or candidate_features.has_instrument_terms:
            score += SCORE_WEIGHTS["query_wants_market_based_match"]
    elif candidate_features.has_instrument_terms:
        score -= SCORE_WEIGHTS["unexpected_instrument_penalty"]

    seasonally_adjusted = candidate_is_seasonally_adjusted(candidate)
    if query_features.wants_seasonally_adjusted is True:
        if seasonally_adjusted is True:
            score += SCORE_WEIGHTS["seasonal_adjustment_match"]
        elif seasonally_adjusted is False:
            score -= SCORE_WEIGHTS["seasonal_adjustment_penalty"]
    elif query_features.wants_seasonally_adjusted is False:
        if seasonally_adjusted is False:
            score += SCORE_WEIGHTS["seasonal_adjustment_match"]
        elif seasonally_adjusted is True:
            score -= SCORE_WEIGHTS["seasonal_adjustment_penalty"]

    return score


def is_plain_inflation_request(search_variants: list[str]) -> bool:
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


def candidate_has_any(candidate: SeriesSearchMatch, terms: tuple[str, ...]) -> bool:
    text = candidate_text(candidate)
    return any(term in text for term in terms)


def has_specialized_inflation_variant(candidate: SeriesSearchMatch) -> bool:
    return candidate_has_any(
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


def is_base_price_index(candidate: SeriesSearchMatch) -> bool:
    text = candidate_text(candidate)
    if not (
        "consumer price index" in text
        or "personal consumption expenditures" in text
        or re.search(r"\bcpi\b", text)
        or re.search(r"\bpce\b", text)
    ):
        return False
    return "index" in text and not has_specialized_inflation_variant(candidate)


def inflation_profile_score_adjustment(
    candidate: SeriesSearchMatch,
    *,
    context: MatchScoreContext,
    candidate_features: CandidateFeatures,
) -> float:
    if not is_plain_inflation_request(list(context.search_variants)):
        return 0.0

    score = 0.0
    if is_base_price_index(candidate):
        score += SCORE_WEIGHTS["inflation_base_index_bonus"]
    if has_specialized_inflation_variant(candidate):
        score -= SCORE_WEIGHTS["inflation_specialized_penalty"]
    if candidate_features.has_instrument_terms and not context.query_features.wants_market_based:
        score -= SCORE_WEIGHTS["inflation_unwanted_instrument_penalty"]
    return score


def score_candidate(
    candidate: SeriesSearchMatch,
    *,
    context: MatchScoreContext,
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

    candidate_features = extract_candidate_features(candidate)
    score = 0.0
    title_matches = 0
    for term in context.anchor_terms:
        if term in title_text:
            score += SCORE_WEIGHTS["anchor_term_title_match"]
            title_matches += 1
        elif term in full_text:
            score += SCORE_WEIGHTS["anchor_term_full_text_match"]

    for phrase in context.search_variants:
        lowered_phrase = phrase.lower().strip()
        if not lowered_phrase:
            continue
        if lowered_phrase in full_text:
            score += SCORE_WEIGHTS["exact_phrase_match"]
            continue

        phrase_terms = significant_terms([phrase])
        if phrase_terms:
            matched_terms = sum(1 for term in phrase_terms if term in title_text)
            if matched_terms >= max(1, min(2, len(phrase_terms))):
                score += SCORE_WEIGHTS["partial_phrase_match"]

    if candidate.popularity is not None:
        score += min(
            candidate.popularity / SCORE_WEIGHTS["popularity_divisor"],
            SCORE_WEIGHTS["popularity_cap"],
        )

    if title_matches == 0:
        score -= SCORE_WEIGHTS["no_title_match_penalty"]

    score += generic_score_adjustment(candidate, candidate_features, context=context)
    score += inflation_profile_score_adjustment(
        candidate,
        context=context,
        candidate_features=candidate_features,
    )
    return score


def build_match_score_context(intent: QueryIntent) -> MatchScoreContext | None:
    search_text = clarification_search_text(intent)
    if not search_text:
        return None

    example_searches = extract_clarification_examples(intent.clarification_question)
    search_variants: list[str] = []
    for value in [*example_searches, search_text]:
        normalized = value.strip()
        if normalized and normalized not in search_variants:
            search_variants.append(normalized)

    context_texts = context_texts_for_intent(
        intent,
        search_text=search_text,
        example_searches=example_searches,
    )
    anchor_terms = significant_terms(context_texts)
    query_text = " ".join(part for part in context_texts if part)
    return MatchScoreContext(
        search_text=search_text,
        example_searches=tuple(example_searches),
        search_variants=tuple(search_variants),
        anchor_terms=tuple(anchor_terms),
        query_features=extract_query_features(query_text),
    )
