from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

import pytest

from fred_query.config import get_settings
from fred_query.schemas.intent import QueryIntent
from fred_query.services.openai_parser_service import OpenAIIntentParser


pytestmark = pytest.mark.evals

_CASE_PATH = Path(__file__).with_name("intent_cases.json")


@dataclass(slots=True)
class EvalResult:
    case_id: str
    query: str
    passed: bool
    details: str


def _load_cases() -> list[dict[str, Any]]:
    return json.loads(_CASE_PATH.read_text(encoding="utf-8"))


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _normalized_text(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def _truncate(value: str, *, limit: int = 72) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."


def _combined_search_text(intent: QueryIntent) -> str:
    search_parts = [intent.search_text, *intent.search_texts]
    return " ".join(part for part in search_parts if part).strip()


def _assert_scalar_expectations(intent: QueryIntent, expect: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    scalar_fields = (
        "task_type",
        "transform",
        "clarification_needed",
        "clarification_target_index",
        "cross_section_scope",
        "rank_limit",
        "sort_descending",
        "transform_window",
        "series_id",
        "normalization",
    )
    for field_name in scalar_fields:
        if field_name not in expect:
            continue
        actual_value = _enum_value(getattr(intent, field_name))
        expected_value = expect[field_name]
        if actual_value != expected_value:
            failures.append(
                f"expected {field_name}={expected_value!r}, got {actual_value!r}"
            )
    return failures


def _assert_date_expectations(intent: QueryIntent, expect: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for field_name in ("start_date", "end_date", "observation_date"):
        if field_name not in expect:
            continue
        actual_value = getattr(intent, field_name)
        actual_text = actual_value.isoformat() if actual_value is not None else None
        if actual_text != expect[field_name]:
            failures.append(
                f"expected {field_name}={expect[field_name]!r}, got {actual_text!r}"
            )
    return failures


def _assert_search_expectations(intent: QueryIntent, expect: dict[str, Any]) -> list[str]:
    failures: list[str] = []

    if "search_text_contains" in expect:
        combined_search_text = _normalized_text(_combined_search_text(intent))
        raw_expected = expect["search_text_contains"]
        expected_fragments = raw_expected if isinstance(raw_expected, list) else [raw_expected]
        missing = [
            fragment
            for fragment in expected_fragments
            if _normalized_text(fragment) not in combined_search_text
        ]
        if missing:
            failures.append(
                "combined search text missing fragments "
                f"{missing!r}; actual={_combined_search_text(intent)!r}"
            )

    if "search_texts_count" in expect and len(intent.search_texts) != expect["search_texts_count"]:
        failures.append(
            f"expected search_texts_count={expect['search_texts_count']}, got {len(intent.search_texts)}"
        )

    if "search_texts_include" in expect:
        normalized_search_texts = [_normalized_text(value) for value in intent.search_texts]
        missing = [
            fragment
            for fragment in expect["search_texts_include"]
            if not any(_normalized_text(fragment) in value for value in normalized_search_texts)
        ]
        if missing:
            failures.append(
                f"search_texts missing fragments {missing!r}; actual={intent.search_texts!r}"
            )

    return failures


def _assert_geography_expectations(intent: QueryIntent, expect: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if "geographies_include" not in expect:
        return failures

    normalized_geographies = {_normalized_text(geography.name) for geography in intent.geographies}
    missing = [
        geography
        for geography in expect["geographies_include"]
        if _normalized_text(geography) not in normalized_geographies
    ]
    if missing:
        failures.append(
            f"geographies missing {missing!r}; actual={[geography.name for geography in intent.geographies]!r}"
        )
    return failures


def _evaluate_case(parser: OpenAIIntentParser, case: dict[str, Any]) -> EvalResult:
    case_id = case.get("id", case["query"])
    query = case["query"]
    expect = case["expect"]

    try:
        intent = parser.parse(query)
    except Exception as exc:
        return EvalResult(
            case_id=case_id,
            query=query,
            passed=False,
            details=f"parser raised {type(exc).__name__}: {exc}",
        )

    failures = [
        *_assert_scalar_expectations(intent, expect),
        *_assert_date_expectations(intent, expect),
        *_assert_search_expectations(intent, expect),
        *_assert_geography_expectations(intent, expect),
    ]
    summary = (
        f"task_type={_enum_value(intent.task_type)!r}, "
        f"transform={_enum_value(intent.transform)!r}, "
        f"clarification_needed={intent.clarification_needed!r}, "
        f"search={_truncate(_combined_search_text(intent) or '<none>')!r}"
    )
    if failures:
        return EvalResult(
            case_id=case_id,
            query=query,
            passed=False,
            details=f"{summary}; " + "; ".join(failures),
        )
    return EvalResult(case_id=case_id, query=query, passed=True, details=summary)


def _write_scorecard(
    request: pytest.FixtureRequest,
    *,
    model: str,
    reasoning_effort: str,
    results: list[EvalResult],
) -> None:
    passed_count = sum(1 for result in results if result.passed)
    total_count = len(results)
    lines = [
        f"Intent eval scorecard | model={model} | reasoning_effort={reasoning_effort}",
        *[
            f"[{'PASS' if result.passed else 'FAIL'}] {result.case_id}: {result.details}"
            for result in results
        ],
        f"Passed {passed_count}/{total_count} cases",
    ]

    terminal_reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if terminal_reporter is not None:
        terminal_reporter.write_sep("=", lines[0])
        for line in lines[1:]:
            terminal_reporter.write_line(line)
        return

    print("\n".join(lines))


def _build_live_parser(request: pytest.FixtureRequest) -> tuple[OpenAIIntentParser, str, str]:
    get_settings.cache_clear()
    settings = get_settings()
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")
    if not api_key:
        pytest.fail("OPENAI_API_KEY is required when running live intent evals.")

    model = request.config.getoption("--eval-model") or os.getenv("INTENT_EVAL_MODEL") or settings.openai_model
    reasoning_effort = (
        request.config.getoption("--eval-reasoning-effort")
        or os.getenv("INTENT_EVAL_REASONING_EFFORT")
        or settings.openai_reasoning_effort
    )
    parser = OpenAIIntentParser(
        api_key=api_key,
        model=model,
        reasoning_effort=reasoning_effort,
    )
    return parser, model, reasoning_effort


def test_live_intent_eval_cases(request: pytest.FixtureRequest) -> None:
    parser, model, reasoning_effort = _build_live_parser(request)
    results = [_evaluate_case(parser, case) for case in _load_cases()]
    _write_scorecard(request, model=model, reasoning_effort=reasoning_effort, results=results)

    failures = [result for result in results if not result.passed]
    if failures:
        failure_lines = [
            f"{result.case_id}: {result.details}\nquery={result.query!r}"
            for result in failures
        ]
        pytest.fail("Intent eval failures:\n" + "\n\n".join(failure_lines))
