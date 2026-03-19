from __future__ import annotations

from datetime import date

from fred_query.schemas.analysis import ObservationPoint
from fred_query.schemas.chart import DateSpanAnnotation


class TransformService:
    """Deterministic transforms and derived metrics."""

    @staticmethod
    def normalize_to_index(
        observations: list[ObservationPoint],
        *,
        base_value: float = 100.0,
    ) -> list[ObservationPoint]:
        if not observations:
            return []

        first_value = observations[0].value
        if first_value == 0:
            raise ValueError("Cannot normalize a series with a zero starting value.")

        return [
            ObservationPoint(date=point.date, value=(point.value / first_value) * base_value)
            for point in observations
        ]

    @staticmethod
    def calculate_total_growth_pct(observations: list[ObservationPoint]) -> float | None:
        if len(observations) < 2:
            return None

        first_value = observations[0].value
        last_value = observations[-1].value
        if first_value == 0:
            return None

        return ((last_value / first_value) - 1.0) * 100.0

    @staticmethod
    def calculate_cagr_pct(observations: list[ObservationPoint]) -> float | None:
        if len(observations) < 2:
            return None

        first_point = observations[0]
        last_point = observations[-1]
        years = (last_point.date - first_point.date).days / 365.25
        if years <= 0 or first_point.value == 0:
            return None

        return ((last_point.value / first_point.value) ** (1.0 / years) - 1.0) * 100.0

    @staticmethod
    def latest_value(observations: list[ObservationPoint]) -> tuple[float | None, date | None]:
        if not observations:
            return None, None
        last_point = observations[-1]
        return last_point.value, last_point.date

    @staticmethod
    def derive_recession_periods(observations: list[ObservationPoint]) -> list[DateSpanAnnotation]:
        if not observations:
            return []

        recession_dates = [point.date for point in observations if point.value >= 1.0]
        if not recession_dates:
            return []

        periods: list[DateSpanAnnotation] = []
        start = recession_dates[0]
        previous = recession_dates[0]

        for current in recession_dates[1:]:
            if (current - previous).days > 40:
                periods.append(DateSpanAnnotation(label="Recession", start_date=start, end_date=previous))
                start = current
            previous = current

        periods.append(DateSpanAnnotation(label="Recession", start_date=start, end_date=previous))
        return periods
