from __future__ import annotations

from fred_query.schemas.analysis import AnalysisResult, HistoricalSeriesContext
from fred_query.schemas.intent import QueryIntent


class AnswerService:
    """Deterministic answer synthesis for the initial workflow."""

    @staticmethod
    def _metric_value(analysis: AnalysisResult, name: str):
        for metric in analysis.derived_metrics:
            if metric.name == name:
                return metric.value
        return None

    @staticmethod
    def _metric_unit(analysis: AnalysisResult, name: str) -> str | None:
        for metric in analysis.derived_metrics:
            if metric.name == name:
                return metric.unit
        return None

    @staticmethod
    def _format_series_value(value: float, units: str | None) -> str:
        formatted = f"{value:,.2f}"
        normalized = (units or "").strip().lower()
        if "percent" in normalized:
            return f"{formatted}%"
        if "basis point" in normalized or normalized == "bps":
            return f"{formatted} bps"
        return formatted

    @staticmethod
    def _value_label(title: str, units: str | None) -> str:
        normalized_title = title.lower()
        normalized_units = (units or "").lower()
        if "rate" in normalized_title or "percent" in normalized_units:
            return "rate"
        return "value"

    @staticmethod
    def _join_clauses(clauses: list[str]) -> str:
        if not clauses:
            return ""
        if len(clauses) == 1:
            return clauses[0]
        if len(clauses) == 2:
            return f"{clauses[0]} and {clauses[1]}"
        return f"{', '.join(clauses[:-1])}, and {clauses[-1]}"

    @staticmethod
    def _ordinal(value: int) -> str:
        if 10 <= value % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
        return f"{value}{suffix}"

    @staticmethod
    def _historical_window_label(context: HistoricalSeriesContext) -> str:
        span_years = max(1, int(round((context.end_date - context.start_date).days / 365.25)))
        return f"{span_years}-year"

    @staticmethod
    def _distance_qualifier(current_value: float, boundary_value: float, opposite_boundary_value: float) -> str:
        span = abs(boundary_value - opposite_boundary_value)
        if span <= 0:
            return ""

        gap_ratio = abs(boundary_value - current_value) / span
        if gap_ratio >= 0.6:
            return "well "
        if gap_ratio <= 0.15:
            return "just "
        return ""

    @staticmethod
    def _latest_display_point(
        analysis: AnalysisResult,
        *,
        normalize: bool,
    ) -> tuple[float | None, object | None, str | None, str | None]:
        result = analysis.series_results[0]
        if result.analysis_basis and result.transformed_observations:
            latest_point = result.transformed_observations[-1]
            return (
                latest_point.value,
                latest_point.date,
                result.analysis_units or result.series.units,
                result.analysis_basis.lower(),
            )
        return result.latest_value, result.latest_observation_date, result.series.units, None

    def _historical_context_sentence(self, analysis: AnalysisResult, *, normalize: bool) -> str | None:
        result = analysis.series_results[0]
        context = result.historical_context
        latest_value, _, latest_units, subject_basis = self._latest_display_point(analysis, normalize=normalize)
        if context is None or context.observation_count < 2 or latest_value is None:
            return None

        value_label = subject_basis or self._value_label(result.series.title, latest_units)
        window_label = self._historical_window_label(context)
        clauses: list[str] = []

        if context.average_value is not None:
            if latest_value > context.average_value:
                average_relationship = "above"
            elif latest_value < context.average_value:
                average_relationship = "below"
            else:
                average_relationship = "in line with"
            clauses.append(
                f"The latest {value_label} of {self._format_series_value(latest_value, latest_units)} "
                f"is {average_relationship} the {window_label} average of "
                f"{self._format_series_value(context.average_value, latest_units)}"
            )
        else:
            clauses.append(
                f"The latest {value_label} is {self._format_series_value(latest_value, latest_units)}"
            )

        if context.percentile_rank is not None:
            percentile = max(1, min(100, int(round(context.percentile_rank))))
            clauses.append(f"sits in the {self._ordinal(percentile)} percentile of that window")

        if (
            context.max_value is not None
            and context.max_date is not None
            and context.min_value is not None
        ):
            if abs(latest_value - context.max_value) < 1e-9:
                clauses.append("matches the high for that window")
            else:
                qualifier = self._distance_qualifier(
                    latest_value,
                    context.max_value,
                    context.min_value,
                )
                clauses.append(
                    f"is {qualifier}below the {context.max_date.year} peak of "
                    f"{self._format_series_value(context.max_value, latest_units)}"
                )
        elif (
            context.min_value is not None
            and context.min_date is not None
            and context.max_value is not None
        ):
            if abs(latest_value - context.min_value) < 1e-9:
                clauses.append("matches the low for that window")
            else:
                qualifier = self._distance_qualifier(
                    latest_value,
                    context.min_value,
                    context.max_value,
                )
                clauses.append(
                    f"is {qualifier}above the {context.min_date.year} trough of "
                    f"{self._format_series_value(context.min_value, latest_units)}"
                )

        summary = self._join_clauses(clauses)
        return f"{summary}." if summary else None

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
        latest_display_value, latest_display_date, latest_display_units, latest_basis = self._latest_display_point(
            analysis,
            normalize=normalize,
        )

        parts = [
            f"Retrieved {result.series.title} from {start_year} to {end_year}.",
        ]
        if latest_display_value is not None and latest_display_date is not None and latest_basis:
            parts.append(
                f"The latest {latest_basis} reading is "
                f"{self._format_series_value(latest_display_value, latest_display_units)} "
                f"on {latest_display_date.isoformat()}."
            )
        elif result.latest_value is not None and result.latest_observation_date is not None:
            parts.append(
                f"The latest observation is "
                f"{self._format_series_value(result.latest_value, result.series.units)} "
                f"on {result.latest_observation_date.isoformat()}."
            )
        historical_context_sentence = self._historical_context_sentence(analysis, normalize=normalize)
        if historical_context_sentence:
            parts.append(historical_context_sentence)
        if result.total_growth_pct is not None:
            parts.append(f"Total growth over the period was {result.total_growth_pct:.2f}%.")
        if result.analysis_basis:
            parts.append(f"The chart shows {result.analysis_basis.lower()}.")
        elif normalize:
            parts.append("The chart is normalized to an index of 100 at the first observation.")
        else:
            parts.append("The chart uses reported levels.")
        parts.append(f"Series used: {result.series.series_id}.")
        return " ".join(parts)

    def write_relationship_analysis(self, analysis: AnalysisResult) -> str:
        first, second = analysis.series_results
        start_year = analysis.coverage_start.year if analysis.coverage_start else "the requested start"
        end_year = analysis.coverage_end.year if analysis.coverage_end else "the latest available year"
        summary = analysis.relationship_summary
        frequency = summary.common_frequency if summary is not None else self._metric_value(analysis, "common_frequency")
        basis = summary.analysis_basis if summary is not None else self._metric_value(analysis, "analysis_basis")
        overlap = (
            summary.overlap_observations if summary is not None else self._metric_value(analysis, "overlap_observations")
        )
        same_period_correlation = (
            summary.same_period_correlation
            if summary is not None
            else self._metric_value(analysis, "same_period_correlation")
        )
        strongest_lag = (
            summary.strongest_lag_periods if summary is not None else self._metric_value(analysis, "strongest_lag_periods")
        )
        strongest_lag_correlation = (
            summary.strongest_lag_correlation
            if summary is not None
            else self._metric_value(analysis, "strongest_lag_correlation")
        )
        lag_unit = (
            summary.strongest_lag_unit
            if summary is not None and summary.strongest_lag_unit
            else self._metric_unit(analysis, "strongest_lag_periods") or "periods"
        )

        parts = [
            f"Analyzed the relationship between {first.series.title} and {second.series.title} from {start_year} to {end_year}.",
        ]
        if frequency and basis:
            parts.append(f"The analysis uses {str(frequency).lower()} aligned data with {basis}.")
        if same_period_correlation is not None and overlap is not None:
            parts.append(
                f"The same-period correlation is {float(same_period_correlation):.2f} across {int(overlap)} overlapping observations."
            )
        if strongest_lag is not None and strongest_lag_correlation is not None:
            lag_value = int(strongest_lag)
            if lag_value > 0:
                lag_text = f"{first.series.series_id} leads {second.series.series_id} by {lag_value} {lag_unit}"
            elif lag_value < 0:
                lag_text = f"{second.series.series_id} leads {first.series.series_id} by {abs(lag_value)} {lag_unit}"
            else:
                lag_text = "the strongest relationship is contemporaneous"
            parts.append(
                f"In the tested lead-lag window, the strongest absolute correlation is {float(strongest_lag_correlation):.2f}, "
                f"and {lag_text}."
            )
        parts.append("This is an association estimate, not evidence of causation.")
        parts.append(f"Series used: {first.series.series_id} and {second.series.series_id}.")
        return " ".join(parts)

    def write_cross_section(self, analysis: AnalysisResult, *, intent: QueryIntent) -> str:
        leader = analysis.series_results[0]
        summary = analysis.cross_section_summary
        snapshot_basis = (
            summary.snapshot_basis
            if summary is not None
            else self._metric_value(analysis, "snapshot_basis") or "Latest available observation"
        )
        displayed_count = (
            summary.displayed_series_count if summary is not None else self._metric_value(analysis, "displayed_series_count")
        )
        resolved_count = (
            summary.resolved_series_count if summary is not None else self._metric_value(analysis, "resolved_series_count")
        )
        display_selection_basis = (
            summary.display_selection_basis
            if summary is not None
            else self._metric_value(analysis, "display_selection_basis")
        )
        rank_label = summary.rank_order if summary is not None else ("highest" if intent.sort_descending else "lowest")

        if int(resolved_count or len(analysis.series_results)) == 1:
            parts = [
                f"Retrieved a point-in-time cross-section for {leader.series.title}.",
            ]
            if leader.latest_value is not None and leader.latest_observation_date is not None:
                parts.append(
                    f"The observed value is {leader.latest_value:,.2f} on {leader.latest_observation_date.isoformat()}."
                )
            parts.append(f"Observation basis: {snapshot_basis}.")
            parts.append(f"Series used: {leader.series.series_id}.")
            return " ".join(parts)

        parts = [
            f"Ranked {displayed_count or len(analysis.series_results)} series by their {rank_label} value.",
            f"Observation basis: {snapshot_basis}.",
        ]
        if leader.latest_value is not None and leader.latest_observation_date is not None:
            parts.append(
                f"{leader.series.geography} ranks {rank_label} at {leader.latest_value:,.2f} "
                f"on {leader.latest_observation_date.isoformat()}."
            )
        if (
            display_selection_basis == "comparison_context"
            and resolved_count
            and displayed_count
            and int(resolved_count) > int(displayed_count)
        ):
            parts.append(
                f"The chart shows {int(displayed_count)} ranked series to provide comparison context around the leader."
            )
        elif (
            resolved_count
            and displayed_count
            and int(resolved_count) > int(displayed_count)
        ):
            parts.append(
                f"The chart shows the requested slice of {int(displayed_count)} out of {int(resolved_count)} resolved series."
            )
        else:
            parts.append("The chart shows the full ranked cross-section rather than a time-series trend.")
        parts.append("Bars are sorted by the requested ranking direction.")
        return " ".join(parts)
