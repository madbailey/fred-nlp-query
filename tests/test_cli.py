from __future__ import annotations

from contextlib import redirect_stdout
from datetime import date
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fred_query.cli import main
from fred_query.schemas.analysis import AnalysisResult, QueryResponse, RoutedQueryResponse, RoutedQueryStatus, SeriesAnalysis
from fred_query.schemas.chart import AxisSpec, ChartSpec, ChartTrace
from fred_query.schemas.intent import ComparisonMode, Geography, GeographyType, QueryIntent, TaskType, TransformType
from fred_query.schemas.resolved_series import ResolvedSeries


def _build_response() -> QueryResponse:
    first_series = ResolvedSeries(
        series_id="CARGSP",
        title="Real GDP: California",
        geography="California",
        indicator="real_gdp",
        units="Millions of Chained 2017 Dollars",
        frequency="A",
        seasonal_adjustment="NSA",
        resolution_reason="Test fixture",
        source_url="https://fred.stlouisfed.org/series/CARGSP",
    )
    second_series = ResolvedSeries(
        series_id="TXRGSP",
        title="Real GDP: Texas",
        geography="Texas",
        indicator="real_gdp",
        units="Millions of Chained 2017 Dollars",
        frequency="A",
        seasonal_adjustment="NSA",
        resolution_reason="Test fixture",
        source_url="https://fred.stlouisfed.org/series/TXRGSP",
    )

    return QueryResponse(
        intent=QueryIntent(
            task_type=TaskType.STATE_GDP_COMPARISON,
            indicators=["real_gdp"],
            geographies=[
                Geography(name="California", geography_type=GeographyType.STATE),
                Geography(name="Texas", geography_type=GeographyType.STATE),
            ],
            comparison_mode=ComparisonMode.STATE_VS_STATE,
            start_date=date(2019, 1, 1),
            end_date=date(2023, 12, 31),
            transform=TransformType.NORMALIZED_INDEX,
            normalization=True,
        ),
        analysis=AnalysisResult(
            series_results=[
                SeriesAnalysis(series=first_series, latest_value=1.0, latest_observation_date=date(2023, 1, 1)),
                SeriesAnalysis(series=second_series, latest_value=2.0, latest_observation_date=date(2023, 1, 1)),
            ],
            latest_observation_date=date(2023, 1, 1),
            coverage_start=date(2019, 1, 1),
            coverage_end=date(2023, 1, 1),
        ),
        chart=ChartSpec(
            title="Real GDP Comparison: California vs Texas",
            subtitle="Fixture",
            x_axis=AxisSpec(title="Date"),
            y_axis=AxisSpec(title="Index (Base = 100)"),
            series=[
                ChartTrace(name="California", x=[date(2019, 1, 1)], y=[100.0]),
                ChartTrace(name="Texas", x=[date(2019, 1, 1)], y=[100.0]),
            ],
            source_note="Source: FRED, Federal Reserve Bank of St. Louis",
        ),
        answer_text="Fixture answer text.",
    )


class CLITest(unittest.TestCase):
    @patch("fred_query.cli.run_compare_state_gdp")
    def test_text_output(self, mock_run_compare_state_gdp) -> None:
        mock_run_compare_state_gdp.return_value = _build_response()
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "compare-state-gdp",
                    "--state1",
                    "California",
                    "--state2",
                    "Texas",
                    "--start-date",
                    "2019-01-01",
                ]
            )

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("Fixture answer text.", output)
        self.assertIn("CARGSP", output)
        self.assertIn("Real GDP Comparison: California vs Texas", output)

    @patch("fred_query.cli.run_compare_state_gdp")
    def test_json_output_and_chart_write(self, mock_run_compare_state_gdp) -> None:
        mock_run_compare_state_gdp.return_value = _build_response()
        stdout = io.StringIO()

        with TemporaryDirectory() as tmpdir:
            chart_path = Path(tmpdir) / "chart-spec.json"
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "compare-state-gdp",
                        "--state1",
                        "California",
                        "--state2",
                        "Texas",
                        "--start-date",
                        "2019-01-01",
                        "--format",
                        "json",
                        "--chart-spec-out",
                        str(chart_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["chart"]["title"], "Real GDP Comparison: California vs Texas")
            self.assertTrue(chart_path.exists())
            chart_spec_payload = json.loads(chart_path.read_text(encoding="utf-8"))
            self.assertEqual(chart_spec_payload["layout"]["title"]["text"], "Real GDP Comparison: California vs Texas")

    @patch("fred_query.cli.run_natural_language_query")
    def test_ask_command_text_output(self, mock_run_natural_language_query) -> None:
        mock_run_natural_language_query.return_value = RoutedQueryResponse(
            status=RoutedQueryStatus.NEEDS_CLARIFICATION,
            intent=_build_response().intent,
            answer_text="Do you mean CPI or PCE inflation?",
        )
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = main(["ask", "Show me inflation."])

        self.assertEqual(exit_code, 0)
        self.assertIn("CPI or PCE", stdout.getvalue())

    @patch("fred_query.cli.run_natural_language_query")
    def test_ask_command_returns_hard_error(self, mock_run_natural_language_query) -> None:
        mock_run_natural_language_query.side_effect = RuntimeError("insufficient_quota")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), patch.object(sys, "stderr", stderr):
            exit_code = main(["ask", "Show me inflation."])

        self.assertEqual(exit_code, 1)
        self.assertIn("natural-language parsing failed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
