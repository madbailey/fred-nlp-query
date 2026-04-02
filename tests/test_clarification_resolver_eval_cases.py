from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from fred_query.schemas.intent import QueryIntent
from fred_query.schemas.resolved_series import SeriesSearchMatch
from fred_query.services.clarification_resolver import ClarificationResolver


_CASE_PATH = Path(__file__).with_name("clarification_resolver_eval_cases.json")


class _FixtureFREDClient:
    def __init__(self, search_results: dict[str, list[dict[str, Any]]]) -> None:
        self.search_results = {
            self._normalize_query(query): [SeriesSearchMatch(**item) for item in items]
            for query, items in search_results.items()
        }

    @staticmethod
    def _normalize_query(query: str) -> str:
        return " ".join(query.lower().split())

    def search_series(self, search_text: str, limit: int = 6) -> list[SeriesSearchMatch]:
        return list(self.search_results.get(self._normalize_query(search_text), []))[:limit]


def _load_cases() -> list[dict[str, Any]]:
    return json.loads(_CASE_PATH.read_text(encoding="utf-8"))


def _evaluate_case(case: dict[str, Any]) -> list[str]:
    resolver = ClarificationResolver(_FixtureFREDClient(case["search_results"]))
    intent = QueryIntent(**case["intent"])
    candidates = resolver.build_candidates(intent)
    expect = case["expect"]
    failures: list[str] = []

    if "series_ids" in expect:
        actual_series_ids = [candidate.series_id for candidate in candidates]
        if actual_series_ids != expect["series_ids"]:
            failures.append(f"expected series_ids={expect['series_ids']!r}, got {actual_series_ids!r}")

    if "selection_labels" in expect:
        actual_selection_labels = [candidate.selection_label for candidate in candidates]
        if actual_selection_labels != expect["selection_labels"]:
            failures.append(
                f"expected selection_labels={expect['selection_labels']!r}, got {actual_selection_labels!r}"
            )

    if "clarification_option_labels" in expect:
        actual_option_labels = [
            candidate.clarification_option.label if candidate.clarification_option is not None else None
            for candidate in candidates
        ]
        if actual_option_labels != expect["clarification_option_labels"]:
            failures.append(
                "expected clarification_option_labels="
                f"{expect['clarification_option_labels']!r}, got {actual_option_labels!r}"
            )

    if "selection_hints_contain" in expect:
        actual_hints = [candidate.selection_hint or "" for candidate in candidates]
        for index, fragment in enumerate(expect["selection_hints_contain"]):
            if index >= len(actual_hints) or fragment not in actual_hints[index]:
                failures.append(
                    f"expected selection_hint[{index}] to contain {fragment!r}, got "
                    f"{actual_hints[index] if index < len(actual_hints) else None!r}"
                )

    if "selection_badges_include" in expect:
        actual_badges = [candidate.selection_badges for candidate in candidates]
        for index, expected_badges in enumerate(expect["selection_badges_include"]):
            if index >= len(actual_badges):
                failures.append(f"missing candidate at index {index} for selection_badges_include")
                continue
            missing = [badge for badge in expected_badges if badge not in actual_badges[index]]
            if missing:
                failures.append(
                    f"selection_badges[{index}] missing {missing!r}; actual={actual_badges[index]!r}"
                )

    if "clarification_option_badges_include" in expect:
        actual_option_badges = [
            [badge.label for badge in (candidate.clarification_option.badges if candidate.clarification_option else [])]
            for candidate in candidates
        ]
        for index, expected_badges in enumerate(expect["clarification_option_badges_include"]):
            if index >= len(actual_option_badges):
                failures.append(f"missing candidate at index {index} for clarification_option_badges_include")
                continue
            missing = [badge for badge in expected_badges if badge not in actual_option_badges[index]]
            if missing:
                failures.append(
                    "clarification_option_badges["
                    f"{index}] missing {missing!r}; actual={actual_option_badges[index]!r}"
                )

    if expect.get("unique_titles"):
        actual_titles = [candidate.title for candidate in candidates]
        if len(actual_titles) != len(set(actual_titles)):
            failures.append(f"expected unique titles, got {actual_titles!r}")

    return failures


@pytest.mark.parametrize("case", _load_cases(), ids=lambda case: case["id"])
def test_clarification_resolver_eval_cases(case: dict[str, Any]) -> None:
    failures = _evaluate_case(case)
    if failures:
        pytest.fail("\n".join(failures))
