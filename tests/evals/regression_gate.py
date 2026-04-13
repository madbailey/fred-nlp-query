from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fred_query.schemas.analysis import AnalysisResult, QueryResponse
from fred_query.schemas.chart import AxisSpec, ChartSpec
from fred_query.schemas.intent import (
    ComparisonMode,
    CrossSectionScope,
    Geography,
    GeographyType,
    QueryIntent,
    QueryOperator,
    QueryOutputMode,
    QueryPlan,
    QueryTimeScope,
    TaskType,
    TransformType,
)
from fred_query.schemas.resolved_series import SeriesMetadata, SeriesSearchMatch
from fred_query.services.clarification_resolver import ClarificationResolver
from fred_query.services.openai_parser_service import OpenAIIntentParser
from fred_query.services.query_router import QueryRouter
from fred_query.services.resolver_service import ResolverService


SNAPSHOT_DIR = Path(__file__).with_name("snapshots")
THRESHOLDS_PATH = SNAPSHOT_DIR / "thresholds.json"
SNAPSHOT_PATHS = {
    "parser": SNAPSHOT_DIR / "parser.json",
    "resolver": SNAPSHOT_DIR / "resolver.json",
    "router": SNAPSHOT_DIR / "router.json",
}


@dataclass(frozen=True)
class SuiteComparison:
    suite: str
    passed: int
    total: int
    pass_rate: float
    baseline_pass_rate: float
    pass_rate_delta: float
    regressions: list[str]
    missing_cases: list[str]
    added_cases: list[str]


class _FakeResponsesAPI:
    def __init__(self, intent: QueryIntent) -> None:
        self.intent = intent

    def parse(self, **_: object) -> object:
        return SimpleNamespace(output_parsed=self.intent)


class _FakeOpenAIClient:
    def __init__(self, intent: QueryIntent) -> None:
        self.responses = _FakeResponsesAPI(intent)


class _RegressionFREDClient:
    def __init__(self) -> None:
        self.metadata = {
            "T10YIE": SeriesMetadata(
                series_id="T10YIE",
                title="10-Year Breakeven Inflation Rate",
                units="Percent",
                frequency="Daily",
                source_url="https://fred.stlouisfed.org/series/T10YIE",
            ),
            "PCEPI": SeriesMetadata(
                series_id="PCEPI",
                title="Personal Consumption Expenditures: Chain-type Price Index",
                units="Index 2017=100",
                frequency="Monthly",
                source_url="https://fred.stlouisfed.org/series/PCEPI",
            ),
            "CPIAUCSL": SeriesMetadata(
                series_id="CPIAUCSL",
                title="Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
                units="Index 1982-1984=100",
                frequency="Monthly",
                source_url="https://fred.stlouisfed.org/series/CPIAUCSL",
            ),
            "GDP": SeriesMetadata(
                series_id="GDP",
                title="Gross Domestic Product",
                units="Billions of Current Dollars",
                frequency="Quarterly",
                seasonal_adjustment="SAAR",
                source_url="https://fred.stlouisfed.org/series/GDP",
            ),
            "A191RL1Q225SBEA": SeriesMetadata(
                series_id="A191RL1Q225SBEA",
                title="Real Gross Domestic Product",
                units="Percent Change from Preceding Period",
                frequency="Quarterly",
                seasonal_adjustment="SAAR",
                source_url="https://fred.stlouisfed.org/series/A191RL1Q225SBEA",
            ),
            "GDPC1": SeriesMetadata(
                series_id="GDPC1",
                title="Real Gross Domestic Product",
                units="Billions of Chained 2017 Dollars",
                frequency="Quarterly",
                seasonal_adjustment="SAAR",
                source_url="https://fred.stlouisfed.org/series/GDPC1",
            ),
            "UNRATE": SeriesMetadata(
                series_id="UNRATE",
                title="Unemployment Rate",
                units="Percent",
                frequency="Monthly",
                seasonal_adjustment="Seasonally Adjusted",
                source_url="https://fred.stlouisfed.org/series/UNRATE",
            ),
            "TXURN": SeriesMetadata(
                series_id="TXURN",
                title="Unemployment Rate in Texas",
                units="Percent",
                frequency="Monthly",
                seasonal_adjustment="Seasonally Adjusted",
                source_url="https://fred.stlouisfed.org/series/TXURN",
            ),
            "CARGSP": SeriesMetadata(
                series_id="CARGSP",
                title="Real Gross Domestic Product: California",
                units="Millions of Chained 2017 Dollars",
                frequency="Annual",
                source_url="https://fred.stlouisfed.org/series/CARGSP",
            ),
            "CAUR": SeriesMetadata(
                series_id="CAUR",
                title="Unemployment Rate in California",
                units="Percent",
                frequency="Monthly",
                seasonal_adjustment="Seasonally Adjusted",
                source_url="https://fred.stlouisfed.org/series/CAUR",
            ),
        }

    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        lowered = search_text.lower()
        if "inflation" in lowered:
            series_ids = ["T10YIE", "PCEPI", "CPIAUCSL"]
        elif "gdp" in lowered:
            series_ids = ["GDP", "A191RL1Q225SBEA", "GDPC1"]
        else:
            series_ids = ["UNRATE", "TXURN"]

        return [
            SeriesSearchMatch(
                series_id=series_id,
                title=self.metadata[series_id].title,
                units=self.metadata[series_id].units,
                frequency=self.metadata[series_id].frequency,
                seasonal_adjustment=self.metadata[series_id].seasonal_adjustment,
                popularity={"T10YIE": 100, "CPIAUCSL": 95, "GDP": 94, "GDPC1": 91}.get(series_id, 72),
                source_url=self.metadata[series_id].source_url,
            )
            for series_id in series_ids
        ][:limit]

    def get_series_metadata(self, series_id: str) -> SeriesMetadata:
        return self.metadata[series_id]


class _SnapshotClarificationResolver(ClarificationResolver):
    def __init__(self) -> None:
        pass

    def build_candidates(self, intent: QueryIntent) -> list[SeriesSearchMatch]:
        return [
            SeriesSearchMatch(
                series_id="UNRATE",
                title="Unemployment Rate",
                source_url="https://fred.stlouisfed.org/series/UNRATE",
            )
        ] if intent.clarification_needed else []

    def answer_text(self, intent: QueryIntent, *, candidate_series: list[object]) -> str:
        return f"clarification:{len(candidate_series)}"


class _SnapshotService:
    def __init__(self, route_name: str) -> None:
        self.route_name = route_name

    def _response(self, intent: QueryIntent) -> QueryResponse:
        return QueryResponse(
            intent=intent,
            analysis=AnalysisResult(coverage_start=date(2020, 1, 1), coverage_end=date(2024, 1, 1)),
            chart=ChartSpec(
                title=self.route_name,
                x_axis=AxisSpec(title="Date"),
                y_axis=AxisSpec(title="Value"),
                source_note="Source: regression fixture",
            ),
            answer_text=f"routed:{self.route_name}",
        )

    def compare(self, **kwargs: object) -> QueryResponse:
        intent = QueryIntent(
            task_type=TaskType.STATE_GDP_COMPARISON,
            geographies=[
                Geography(name=str(kwargs["state1"]), geography_type=GeographyType.STATE),
                Geography(name=str(kwargs["state2"]), geography_type=GeographyType.STATE),
            ],
            start_date=kwargs["start_date"],
            end_date=kwargs["end_date"],
            normalization=bool(kwargs["normalize"]),
            comparison_mode=ComparisonMode.STATE_VS_STATE,
        )
        return self._response(intent)

    def lookup(self, intent: QueryIntent) -> QueryResponse:
        return self._response(intent)

    def analyze(self, intent: QueryIntent) -> QueryResponse:
        return self._response(intent)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parser_result(case_id: str, query: str, intent: QueryIntent) -> dict[str, Any]:
    parser = OpenAIIntentParser(api_key="test-key", client=_FakeOpenAIClient(intent))
    parsed = parser.parse(query)
    return {
        "case_id": case_id,
        "query": query,
        "intent": _jsonable(parsed),
    }


def build_parser_snapshot() -> list[dict[str, Any]]:
    return [
        _parser_result(
            "state_gdp_normalized_index",
            "Compare California and Texas GDP since 2019 as an index",
            QueryIntent(
                task_type=TaskType.STATE_GDP_COMPARISON,
                indicators=["real_gdp"],
                geographies=[
                    Geography(name="California", geography_type=GeographyType.STATE),
                    Geography(name="Texas", geography_type=GeographyType.STATE),
                ],
                comparison_mode=ComparisonMode.STATE_VS_STATE,
                start_date=date(2019, 1, 1),
                transform=TransformType.NORMALIZED_INDEX,
            ),
        ),
        _parser_result(
            "state_gdp_missing_peer_clarifies",
            "Compare California GDP",
            QueryIntent(
                task_type=TaskType.STATE_GDP_COMPARISON,
                geographies=[Geography(name="California", geography_type=GeographyType.STATE)],
            ),
        ),
        _parser_result(
            "relationship_defaults_target_index",
            "What is the relationship between Brent crude and inflation?",
            QueryIntent(
                task_type=TaskType.RELATIONSHIP_ANALYSIS,
                clarification_needed=True,
                clarification_question="Which inflation measure do you mean?",
                search_texts=["brent crude oil price", "inflation united states"],
            ),
        ),
        _parser_result(
            "point_in_time_promotes_cross_section",
            "What was inflation in January 2023?",
            QueryIntent(
                task_type=TaskType.SINGLE_SERIES_LOOKUP,
                indicators=["inflation"],
                search_text="inflation",
                observation_date=date(2023, 1, 1),
            ),
        ),
        _parser_result(
            "cross_section_state_scope_default",
            "Which state has the lowest unemployment rate?",
            QueryIntent(
                task_type=TaskType.CROSS_SECTION,
                indicators=["unemployment rate"],
                search_text="unemployment rate",
            ),
        ),
        _parser_result(
            "rolling_volatility_disables_normalization",
            "How volatile has the S&P 500 been over the last 30 days?",
            QueryIntent(
                task_type=TaskType.SINGLE_SERIES_LOOKUP,
                indicators=["s&p 500"],
                search_text="s&p 500",
                transform=TransformType.ROLLING_VOLATILITY,
                transform_window=30,
            ),
        ),
    ]


def _resolver_result(
    case_id: str,
    resolver: ResolverService,
    **kwargs: Any,
) -> dict[str, Any]:
    resolved, metadata, search_match = resolver.resolve_series(**kwargs)
    return {
        "case_id": case_id,
        "resolved": _jsonable(resolved),
        "metadata_series_id": metadata.series_id,
        "search_match_series_id": search_match.series_id if search_match else None,
    }


def build_resolver_snapshot() -> list[dict[str, Any]]:
    resolver = ResolverService(_RegressionFREDClient())
    return [
        _resolver_result(
            "plain_inflation_prefers_cpi",
            resolver,
            search_text="inflation united states",
            geography="United States",
            indicator="inflation",
        ),
        _resolver_result(
            "real_gdp_prefers_level_series",
            resolver,
            search_text="real gdp united states",
            geography="United States",
            indicator="real gdp",
        ),
        _resolver_result(
            "state_geography_signal_prefers_texas_unemployment",
            resolver,
            search_text="texas unemployment rate",
            geography="Texas",
            indicator="unemployment rate",
        ),
        _resolver_result(
            "explicit_series_id_bypasses_search",
            resolver,
            explicit_series_id="UNRATE",
            geography="United States",
            indicator="unemployment rate",
        ),
        {
            "case_id": "state_gdp_pattern_resolution",
            "resolved": _jsonable(resolver.resolve_state_gdp_series("CA")),
        },
        {
            "case_id": "state_indicator_pattern_resolution",
            "resolved": _jsonable(
                resolver.resolve_state_indicator_series(
                    "California",
                    indicator_hint="unemployment rate",
                )
            ),
        },
    ]


def _router() -> QueryRouter:
    relationship_service = _SnapshotService("relationship")
    return QueryRouter(
        clarification_resolver=_SnapshotClarificationResolver(),
        state_gdp_service=_SnapshotService("state_gdp"),
        cross_section_service=_SnapshotService("cross_section"),
        single_series_service=_SnapshotService("single_series"),
        relationship_service=relationship_service,
    )


def _router_result(
    case_id: str,
    intent: QueryIntent,
    *,
    selected_series_ids: list[str | None] | None = None,
    include_intent: bool = True,
) -> dict[str, Any]:
    response = _router().route(intent, selected_series_ids=selected_series_ids)
    result = {
        "case_id": case_id,
        "status": response.status.value,
        "reason": response.reason.value if response.reason else None,
        "answer_text": response.answer_text,
        "candidate_series_ids": [candidate.series_id for candidate in response.candidate_series],
    }
    if include_intent:
        result["intent"] = _jsonable(response.intent)
    return result


def build_router_snapshot() -> list[dict[str, Any]]:
    many_regions = [
        Geography(name=f"Region {index}", geography_type=GeographyType.REGION)
        for index in range(26)
    ]
    return [
        _router_result(
            "state_gdp_missing_state_requires_clarification",
            QueryIntent(
                task_type=TaskType.STATE_GDP_COMPARISON,
                clarification_needed=True,
                geographies=[Geography(name="California", geography_type=GeographyType.STATE)],
                comparison_mode=ComparisonMode.STATE_VS_STATE,
            ),
        ),
        _router_result(
            "cross_section_many_geographies_needs_threshold",
            QueryIntent(
                task_type=TaskType.CROSS_SECTION,
                clarification_needed=True,
                geographies=many_regions,
                search_text="unemployment rate",
            ),
        ),
        _router_result(
            "selected_series_dispatches_relationship",
            QueryIntent(
                task_type=TaskType.RELATIONSHIP_ANALYSIS,
                comparison_mode=ComparisonMode.RELATIONSHIP,
                clarification_needed=True,
                clarification_target_index=1,
                search_texts=["unemployment rate", "inflation"],
            ),
            selected_series_ids=["UNRATE", "CPIAUCSL"],
        ),
        _router_result(
            "query_plan_overrides_legacy_task_type",
            QueryIntent(
                task_type=TaskType.SINGLE_SERIES_LOOKUP,
                query_plan=QueryPlan(
                    subjects=["unemployment rate", "inflation"],
                    geographies=[],
                    time_scope=QueryTimeScope(),
                    operators=[QueryOperator.ANALYZE_RELATIONSHIP],
                    output_mode=QueryOutputMode.RELATIONSHIP,
                ),
                search_texts=["unemployment rate", "inflation"],
                comparison_mode=ComparisonMode.RELATIONSHIP,
            ),
        ),
        _router_result(
            "single_series_dispatch",
            QueryIntent(
                task_type=TaskType.SINGLE_SERIES_LOOKUP,
                search_text="unemployment rate",
            ),
        ),
        _router_result(
            "unsupported_route_reason",
            QueryIntent.model_construct(task_type="custom_task", query_plan=None),
            include_intent=False,
        ),
    ]


def build_snapshots() -> dict[str, list[dict[str, Any]]]:
    return {
        "parser": build_parser_snapshot(),
        "resolver": build_resolver_snapshot(),
        "router": build_router_snapshot(),
    }


def _case_map(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {case["case_id"]: case for case in cases}


def compare_suite(
    suite: str,
    baseline_cases: list[dict[str, Any]],
    current_cases: list[dict[str, Any]],
) -> SuiteComparison:
    baseline = _case_map(baseline_cases)
    current = _case_map(current_cases)
    common_case_ids = sorted(set(baseline) & set(current))
    regressions = [
        case_id
        for case_id in common_case_ids
        if baseline[case_id] != current[case_id]
    ]
    missing_cases = sorted(set(baseline) - set(current))
    added_cases = sorted(set(current) - set(baseline))
    total = len(baseline_cases)
    passed = total - len(regressions) - len(missing_cases)
    pass_rate = passed / total if total else 0.0
    baseline_pass_rate = 1.0 if total else 0.0
    return SuiteComparison(
        suite=suite,
        passed=passed,
        total=total,
        pass_rate=pass_rate,
        baseline_pass_rate=baseline_pass_rate,
        pass_rate_delta=pass_rate - baseline_pass_rate,
        regressions=regressions,
        missing_cases=missing_cases,
        added_cases=added_cases,
    )


def load_thresholds() -> dict[str, dict[str, float | int]]:
    return json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))


def load_baselines() -> dict[str, list[dict[str, Any]]]:
    return {
        suite: json.loads(path.read_text(encoding="utf-8"))
        for suite, path in SNAPSHOT_PATHS.items()
    }


def update_snapshots() -> None:
    for suite, cases in build_snapshots().items():
        _write_json(SNAPSHOT_PATHS[suite], cases)


def _format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def build_markdown(comparisons: list[SuiteComparison]) -> str:
    lines = [
        "## Regression Snapshot Gate",
        "",
        "| Suite | Pass Rate | Delta vs Baseline | Regressions | Missing | Added |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for comparison in comparisons:
        lines.append(
            f"| {comparison.suite} | "
            f"{comparison.passed}/{comparison.total} ({_format_percent(comparison.pass_rate)}) | "
            f"{comparison.pass_rate_delta:+.3f} | "
            f"{len(comparison.regressions)} | "
            f"{len(comparison.missing_cases)} | "
            f"{len(comparison.added_cases)} |"
        )

    for comparison in comparisons:
        changed = [
            *[f"regressed: {case_id}" for case_id in comparison.regressions],
            *[f"missing: {case_id}" for case_id in comparison.missing_cases],
            *[f"added: {case_id}" for case_id in comparison.added_cases],
        ]
        if changed:
            lines.extend(["", f"### {comparison.suite}", ""])
            lines.extend(f"- {item}" for item in changed)
    return "\n".join(lines) + "\n"


def enforce_thresholds(
    comparisons: list[SuiteComparison],
    thresholds: dict[str, dict[str, float | int]],
) -> list[str]:
    failures: list[str] = []
    for comparison in comparisons:
        suite_thresholds = thresholds[comparison.suite]
        min_pass_rate = float(suite_thresholds["min_pass_rate"])
        max_regressions = int(suite_thresholds["max_regressions"])
        if comparison.pass_rate < min_pass_rate:
            failures.append(
                f"{comparison.suite} pass rate {_format_percent(comparison.pass_rate)} "
                f"is below threshold {_format_percent(min_pass_rate)}"
            )
        if len(comparison.regressions) > max_regressions:
            failures.append(
                f"{comparison.suite} has {len(comparison.regressions)} regressions; "
                f"threshold allows {max_regressions}"
            )
        if comparison.missing_cases:
            failures.append(f"{comparison.suite} is missing cases: {', '.join(comparison.missing_cases)}")
    return failures


def run_gate(summary_out: Path | None) -> int:
    current = build_snapshots()
    baseline = load_baselines()
    comparisons = [
        compare_suite(suite, baseline[suite], current[suite])
        for suite in SNAPSHOT_PATHS
    ]
    markdown = build_markdown(comparisons)
    print(markdown)
    if summary_out is not None:
        summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary_out.write_text(markdown, encoding="utf-8")

    failures = enforce_thresholds(comparisons, load_thresholds())
    if failures:
        print("Regression gate failed:")
        for failure in failures:
            print(f"- {failure}")
        print("Update snapshots only after reviewing intentional behavior changes.")
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare deterministic parser, resolver, and router snapshots against checked-in baselines."
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=None,
        help="Optional markdown output path for CI step summaries.",
    )
    parser.add_argument(
        "--update-snapshots",
        action="store_true",
        help="Rewrite checked-in snapshot baselines from current deterministic behavior.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.update_snapshots:
        update_snapshots()
        return 0
    return run_gate(args.summary_out)


if __name__ == "__main__":
    raise SystemExit(main())
