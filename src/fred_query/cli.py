from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from typing import Callable

from fred_query.config import get_settings
from fred_query.schemas.analysis import QueryResponse, RoutedQueryResponse, RoutedQueryStatus
from fred_query.services import FREDClient, NaturalLanguageQueryService, OpenAIIntentParser, StateGDPComparisonService


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}'. Expected YYYY-MM-DD.") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fred-query", description="Run deterministic FRED analysis workflows.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser(
        "ask",
        help="Parse a natural-language economic question and route it into deterministic FRED execution.",
    )
    ask_parser.add_argument("query", help="Natural-language economic question.")
    ask_parser.add_argument(
        "--format",
        dest="output_format",
        choices=("text", "json"),
        default="text",
        help="Output mode. 'text' prints a readable summary; 'json' prints the structured routed response.",
    )
    ask_parser.add_argument(
        "--chart-spec-out",
        type=Path,
        help="Optional path to write the generated chart spec JSON when the query completes successfully.",
    )

    compare_parser = subparsers.add_parser(
        "compare-state-gdp",
        help="Compare two states' real GDP using the deterministic backend flow.",
    )
    compare_parser.add_argument("--state1", required=True, help="First state name or postal code.")
    compare_parser.add_argument("--state2", required=True, help="Second state name or postal code.")
    compare_parser.add_argument("--start-date", required=True, type=_parse_date, help="Start date in YYYY-MM-DD format.")
    compare_parser.add_argument("--end-date", type=_parse_date, help="Optional end date in YYYY-MM-DD format.")
    compare_parser.add_argument(
        "--format",
        dest="output_format",
        choices=("text", "json"),
        default="text",
        help="Output mode. 'text' prints a readable summary; 'json' prints the full structured response.",
    )
    compare_parser.add_argument(
        "--levels",
        action="store_true",
        help="Use reported levels instead of the default normalized comparison view.",
    )
    compare_parser.add_argument(
        "--chart-spec-out",
        type=Path,
        help="Optional path to write the generated chart spec JSON.",
    )
    return parser


def _render_text_response(response: QueryResponse) -> str:
    lines = [
        response.answer_text,
        "",
        "Series:",
    ]
    for result in response.analysis.series_results:
        lines.append(f"- {result.series.geography}: {result.series.series_id} ({result.series.title})")

    lines.extend(
        [
            "",
            f"Coverage: {response.analysis.coverage_start} to {response.analysis.coverage_end}",
            f"Latest observation date: {response.analysis.latest_observation_date}",
            f"Chart: {response.chart.title}",
            response.chart.source_note,
        ]
    )
    return "\n".join(lines)


def _render_routed_text_response(response: RoutedQueryResponse) -> str:
    if response.status == RoutedQueryStatus.COMPLETED and response.query_response is not None:
        return _render_text_response(response.query_response)

    lines = [response.answer_text]
    if response.candidate_series:
        lines.extend(["", "Candidate series:"])
        for candidate in response.candidate_series:
            lines.append(f"- {candidate.series_id}: {candidate.title}")
    return "\n".join(lines)


def _write_chart_spec(response: QueryResponse, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(response.chart.to_plotly_dict(), indent=2), encoding="utf-8")


def _build_fred_client() -> FREDClient:
    settings = get_settings()
    return FREDClient(
        api_key=settings.fred_api_key or "",
        base_url=settings.fred_base_url,
        timeout_seconds=settings.http_timeout_seconds,
    )


def run_compare_state_gdp(
    args: argparse.Namespace,
    *,
    client_factory: Callable[[], FREDClient] | None = None,
) -> QueryResponse:
    factory = client_factory or _build_fred_client
    client = factory()
    try:
        service = StateGDPComparisonService(client)
        return service.compare(
            state1=args.state1,
            state2=args.state2,
            start_date=args.start_date,
            end_date=args.end_date,
            normalize=not args.levels,
        )
    finally:
        client.close()


def run_natural_language_query(
    args: argparse.Namespace,
    *,
    client_factory: Callable[[], FREDClient] | None = None,
    parser_factory: Callable[[], OpenAIIntentParser] | None = None,
) -> RoutedQueryResponse:
    settings = get_settings()
    client = (client_factory or _build_fred_client)()
    parser = (parser_factory or (lambda: OpenAIIntentParser(
        api_key=settings.openai_api_key or "",
        model=settings.openai_model,
        reasoning_effort=settings.openai_reasoning_effort,
    )))()
    try:
        service = NaturalLanguageQueryService(
            parser=parser,
            fred_client=client,
        )
        return service.ask(args.query)
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "compare-state-gdp":
        response = run_compare_state_gdp(args)

        if args.chart_spec_out:
            _write_chart_spec(response, args.chart_spec_out)

        if args.output_format == "json":
            print(response.model_dump_json(indent=2))
        else:
            print(_render_text_response(response))
        return 0

    if args.command == "ask":
        try:
            response = run_natural_language_query(args)
        except Exception as exc:
            print(f"Error: natural-language parsing failed: {exc}", file=sys.stderr)
            return 1

        if args.chart_spec_out and response.query_response is not None:
            _write_chart_spec(response.query_response, args.chart_spec_out)

        if args.output_format == "json":
            print(response.model_dump_json(indent=2))
        else:
            print(_render_routed_text_response(response))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
