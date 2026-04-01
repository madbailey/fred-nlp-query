from __future__ import annotations

from datetime import date

from fred_query.schemas.analysis import HistoricalSeriesContext, ObservationPoint
from fred_query.schemas.chart import DateSpanAnnotation


class SeriesStatisticsService:
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
    def calculate_average_value(observations: list[ObservationPoint]) -> float | None:
        if not observations:
            return None
        return sum(point.value for point in observations) / len(observations)

    @staticmethod
    def calculate_percentile_rank(
        observations: list[ObservationPoint],
        *,
        value: float | None = None,
    ) -> float | None:
        if len(observations) < 2:
            return None

        reference_value = observations[-1].value if value is None else value
        at_or_below_count = sum(1 for point in observations if point.value <= reference_value)
        return (at_or_below_count / len(observations)) * 100.0

    @staticmethod
    def minimum_point(observations: list[ObservationPoint]) -> ObservationPoint | None:
        if not observations:
            return None
        return min(observations, key=lambda point: (point.value, point.date))

    @staticmethod
    def maximum_point(observations: list[ObservationPoint]) -> ObservationPoint | None:
        if not observations:
            return None
        return max(observations, key=lambda point: (point.value, point.date))

    def summarize_historical_context(
        self,
        observations: list[ObservationPoint],
    ) -> HistoricalSeriesContext | None:
        if not observations:
            return None

        minimum = self.minimum_point(observations)
        maximum = self.maximum_point(observations)
        return HistoricalSeriesContext(
            start_date=observations[0].date,
            end_date=observations[-1].date,
            observation_count=len(observations),
            average_value=self.calculate_average_value(observations),
            percentile_rank=self.calculate_percentile_rank(observations),
            min_value=minimum.value if minimum is not None else None,
            min_date=minimum.date if minimum is not None else None,
            max_value=maximum.value if maximum is not None else None,
            max_date=maximum.date if maximum is not None else None,
        )

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
