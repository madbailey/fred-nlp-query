from __future__ import annotations

from datetime import date

from fred_query.schemas.analysis import SeriesAnalysis
from fred_query.schemas.chart import AxisSpec, ChartSpec, ChartTrace, DateSpanAnnotation, LineStyle


class ChartService:
    """Chart-spec generation for deterministic analysis flows."""

    _COLORS = ["#1f77b4", "#ff7f0e", "#111111"]

    def build_state_gdp_chart(
        self,
        *,
        series_results: list[SeriesAnalysis],
        start_year: int,
        end_year: int,
        normalize: bool,
        recession_periods: list[DateSpanAnnotation],
    ) -> ChartSpec:
        traces: list[ChartTrace] = []
        for index, result in enumerate(series_results):
            points = result.transformed_observations if normalize else result.observations
            if not points:
                continue

            traces.append(
                ChartTrace(
                    name=result.series.geography,
                    x=[point.date for point in points],
                    y=[round(point.value, 4) for point in points],
                    line=LineStyle(color=self._COLORS[index % len(self._COLORS)], width=3 if index == 0 else 2),
                )
            )

        y_axis_title = "Index (Base = 100)" if normalize else series_results[0].series.units
        subtitle = (
            "Normalized to the first observation in the selected range."
            if normalize
            else "Levels shown in FRED-reported units."
        )

        return ChartSpec(
            chart_type="scatter",
            title=f"Real GDP Comparison: {series_results[0].series.geography} vs {series_results[1].series.geography}",
            subtitle=f"{subtitle} Coverage: {start_year} to {end_year}.",
            x_axis=AxisSpec(title="Date"),
            y_axis=AxisSpec(title=y_axis_title),
            series=traces,
            annotations=recession_periods,
            recession_shading=bool(recession_periods),
            source_note="Source: FRED, Federal Reserve Bank of St. Louis",
        )

    def build_single_series_chart(
        self,
        *,
        series_result: SeriesAnalysis,
        start_year: int,
        end_year: int,
        normalize: bool,
        recession_periods: list[DateSpanAnnotation],
    ) -> ChartSpec:
        points = series_result.transformed_observations if normalize else series_result.observations
        y_axis_title = "Index (Base = 100)" if normalize else series_result.series.units

        return ChartSpec(
            chart_type="scatter",
            title=series_result.series.title,
            subtitle=f"Coverage: {start_year} to {end_year}.",
            x_axis=AxisSpec(title="Date"),
            y_axis=AxisSpec(title=y_axis_title),
            series=[
                ChartTrace(
                    name=series_result.series.series_id,
                    x=[point.date for point in points or []],
                    y=[round(point.value, 4) for point in points or []],
                    line=LineStyle(color=self._COLORS[0], width=3),
                )
            ],
            annotations=recession_periods,
            recession_shading=bool(recession_periods),
            source_note="Source: FRED, Federal Reserve Bank of St. Louis",
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
        traces: list[ChartTrace] = []
        for index, result in enumerate(series_results):
            points = result.transformed_observations or []
            traces.append(
                ChartTrace(
                    name=result.series.series_id,
                    x=[point.date for point in points],
                    y=[round(point.value, 4) for point in points],
                    line=LineStyle(color=self._COLORS[index % len(self._COLORS)], width=3 if index == 0 else 2),
                )
            )

        return ChartSpec(
            chart_type="scatter",
            title=f"Relationship Analysis: {series_results[0].series.series_id} vs {series_results[1].series.series_id}",
            subtitle=(
                f"{chart_basis}. {frequency_label} alignment from {start_date.year} to {end_date.year}."
            ),
            x_axis=AxisSpec(title="Date"),
            y_axis=AxisSpec(title=chart_units),
            series=traces,
            source_note="Source: FRED, Federal Reserve Bank of St. Louis",
        )

    def build_cross_section_chart(
        self,
        *,
        series_results: list[SeriesAnalysis],
        title: str,
        subtitle: str,
        y_axis_title: str,
    ) -> ChartSpec:
        ranked_pairs = [
            (
                result.series.geography if result.series.geography != "Unspecified" else result.series.series_id,
                round(result.latest_value, 4),
            )
            for result in series_results
            if result.latest_value is not None
        ]
        return ChartSpec(
            chart_type="bar",
            title=title,
            subtitle=subtitle,
            x_axis=AxisSpec(title="Series"),
            y_axis=AxisSpec(title=y_axis_title),
            series=[
                ChartTrace(
                    name=title,
                    x=[label for label, _ in ranked_pairs],
                    y=[value for _, value in ranked_pairs],
                    line=LineStyle(color=self._COLORS[0]),
                )
            ],
            source_note="Source: FRED, Federal Reserve Bank of St. Louis",
        )
