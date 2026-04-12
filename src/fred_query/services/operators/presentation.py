from __future__ import annotations

from datetime import date

from fred_query.schemas.analysis import AnalysisResult, SeriesAnalysis
from fred_query.schemas.chart import ChartSpec, DateSpanAnnotation
from fred_query.services.answer_service import AnswerService
from fred_query.services.chart_service import ChartService


class BuildChartOp:
    def __init__(self, chart_service: ChartService) -> None:
        self.chart_service = chart_service

    def build_single_series_chart(
        self,
        *,
        series_result: SeriesAnalysis,
        start_year: int,
        end_year: int,
        normalize: bool,
        recession_periods: list[DateSpanAnnotation],
    ) -> ChartSpec:
        return self.chart_service.build_single_series_chart(
            series_result=series_result,
            start_year=start_year,
            end_year=end_year,
            normalize=normalize,
            recession_periods=recession_periods,
        )

    def build_relationship_chart(
        self,
        *,
        series_results: list[SeriesAnalysis],
        frequency_label: str,
        chart_basis: str,
        chart_units: str,
        start_date: date,
        end_date: date,
    ) -> ChartSpec:
        return self.chart_service.build_relationship_chart(
            series_results=series_results,
            frequency_label=frequency_label,
            chart_basis=chart_basis,
            chart_units=chart_units,
            start_date=start_date,
            end_date=end_date,
        )


class RenderAnswerOp:
    def __init__(self, answer_service: AnswerService) -> None:
        self.answer_service = answer_service

    def render_single_series_answer(self, analysis: AnalysisResult, *, normalize: bool) -> str:
        return self.answer_service.write_single_series_lookup(analysis, normalize=normalize)

    def render_relationship_answer(self, analysis: AnalysisResult) -> str:
        return self.answer_service.write_relationship_analysis(analysis)
