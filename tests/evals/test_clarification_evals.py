from __future__ import annotations

from pathlib import Path

import pytest

from tests.evals.intent_eval_harness import (
    build_live_parser,
    evaluate_case,
    load_cases,
    write_json_scorecard,
    write_scorecard,
)


pytestmark = pytest.mark.evals

_CASE_PATH = Path(__file__).with_name("clarification_cases.json")


def test_live_clarification_eval_cases(request: pytest.FixtureRequest) -> None:
    parser, model, reasoning_effort = build_live_parser(request)
    results = [evaluate_case(parser, case) for case in load_cases(_CASE_PATH)]
    write_scorecard(
        request,
        title="Clarification eval scorecard",
        model=model,
        reasoning_effort=reasoning_effort,
        results=results,
    )
    write_json_scorecard(
        request,
        suite="clarification",
        model=model,
        reasoning_effort=reasoning_effort,
        results=results,
    )

    failures = [result for result in results if not result.passed]
    if failures:
        failure_lines = [
            f"{result.case_id}: {result.details}\nquery={result.query!r}"
            for result in failures
        ]
        pytest.fail("Clarification eval failures:\n" + "\n\n".join(failure_lines))
