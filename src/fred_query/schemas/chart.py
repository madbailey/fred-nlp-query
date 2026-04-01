from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class AxisSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str


class LineStyle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    color: str | list[str] | None = None
    width: int | None = None
    dash: str | None = None


class ChartTrace(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    x: list[date] = Field(default_factory=list)
    # Bar charts use categorical x-axis labels here instead of widening `x` to mixed date/string values.
    x_categories: list[str] = Field(default_factory=list)
    y: list[float] = Field(default_factory=list)
    mode: str = "lines"
    line: LineStyle | None = None


class DateSpanAnnotation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str
    start_date: date
    end_date: date
    fillcolor: str = "rgba(128, 128, 128, 0.15)"


class ChartSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chart_type: str = "line"
    title: str
    subtitle: str | None = None
    x_axis: AxisSpec
    y_axis: AxisSpec
    series: list[ChartTrace] = Field(default_factory=list)
    annotations: list[DateSpanAnnotation] = Field(default_factory=list)
    recession_shading: bool = False
    source_note: str

    def to_plotly_dict(self) -> dict[str, object]:
        data = []
        for trace in self.series:
            line = {}
            if trace.line is not None:
                if trace.line.color is not None:
                    line["color"] = trace.line.color
                if trace.line.width is not None:
                    line["width"] = trace.line.width
                if trace.line.dash is not None:
                    line["dash"] = trace.line.dash

            x_values = [point.isoformat() for point in trace.x]
            if self.chart_type == "bar":
                marker = {}
                if trace.line is not None and trace.line.color is not None:
                    marker["color"] = trace.line.color
                data.append(
                    {
                        "type": self.chart_type,
                        "name": trace.name,
                        "x": trace.x_categories,
                        "y": trace.y,
                        "marker": marker,
                    }
                )
                continue

            data.append(
                {
                    "type": self.chart_type,
                    "name": trace.name,
                    "mode": trace.mode,
                    "x": x_values,
                    "y": trace.y,
                    "line": line,
                }
            )

        shapes = []
        for annotation in self.annotations:
            shapes.append(
                {
                    "type": "rect",
                    "xref": "x",
                    "yref": "paper",
                    "x0": annotation.start_date.isoformat(),
                    "x1": annotation.end_date.isoformat(),
                    "y0": 0,
                    "y1": 1,
                    "fillcolor": annotation.fillcolor,
                    "line": {"width": 0},
                    "layer": "below",
                }
            )

        return {
            "data": data,
            "layout": {
                "title": {"text": self.title},
                "xaxis": {"title": self.x_axis.title},
                "yaxis": {"title": self.y_axis.title},
                "annotations": [
                    {
                        "text": self.subtitle,
                        "xref": "paper",
                        "yref": "paper",
                        "x": 0,
                        "y": 1.1,
                        "showarrow": False,
                        "align": "left",
                    }
                ]
                if self.subtitle
                else [],
                "shapes": shapes,
            },
        }
