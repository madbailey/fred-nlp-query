from __future__ import annotations

from fred_query.schemas.analysis import AnalysisResult


class AnswerService:
    """Deterministic answer synthesis for the initial workflow."""

    def write_state_gdp_comparison(self, analysis: AnalysisResult, *, normalize: bool) -> str:
        first, second = analysis.series_results
        start_year = analysis.coverage_start.year if analysis.coverage_start else "the requested start"
        end_year = analysis.coverage_end.year if analysis.coverage_end else "the latest available year"

        parts = [
            f"Compared {first.series.geography} and {second.series.geography} real GDP from {start_year} to {end_year}.",
        ]

        if first.total_growth_pct is not None and second.total_growth_pct is not None:
            parts.append(
                f"{first.series.geography} grew {first.total_growth_pct:.2f}% over the period, while "
                f"{second.series.geography} grew {second.total_growth_pct:.2f}%."
            )
            difference = first.total_growth_pct - second.total_growth_pct
            if difference > 0:
                parts.append(
                    f"{first.series.geography} outpaced {second.series.geography} by {difference:.2f} percentage points."
                )
            elif difference < 0:
                parts.append(
                    f"{second.series.geography} outpaced {first.series.geography} by {abs(difference):.2f} percentage points."
                )
            else:
                parts.append("Both states posted the same total growth over the selected range.")

        if first.latest_value is not None and second.latest_value is not None and second.latest_value != 0:
            ratio = first.latest_value / second.latest_value
            parts.append(
                f"In the latest observation, {first.series.geography}'s economy was {ratio:.2f}x the size of "
                f"{second.series.geography}'s."
            )

        if normalize:
            parts.append("The chart is normalized to an index of 100 at the first observation to emphasize relative growth.")
        else:
            parts.append("The chart uses reported GDP levels.")

        parts.append(f"Series used: {first.series.series_id} and {second.series.series_id}.")
        return " ".join(parts)

    def write_single_series_lookup(self, analysis: AnalysisResult, *, normalize: bool) -> str:
        result = analysis.series_results[0]
        start_year = analysis.coverage_start.year if analysis.coverage_start else "the requested start"
        end_year = analysis.coverage_end.year if analysis.coverage_end else "the latest available year"

        parts = [
            f"Retrieved {result.series.title} from {start_year} to {end_year}.",
        ]
        if result.latest_value is not None and result.latest_observation_date is not None:
            parts.append(
                f"The latest observation is {result.latest_value:,.2f} on {result.latest_observation_date.isoformat()}."
            )
        if result.total_growth_pct is not None:
            parts.append(f"Total growth over the period was {result.total_growth_pct:.2f}%.")
        if normalize:
            parts.append("The chart is normalized to an index of 100 at the first observation.")
        else:
            parts.append("The chart uses reported levels.")
        parts.append(f"Series used: {result.series.series_id}.")
        return " ".join(parts)
