from __future__ import annotations

from datetime import date, timedelta

from fred_query.schemas.intent import TransformType


class TransformPlanningService:
    _DAILY_PERIODS_PER_YEAR = 252

    @classmethod
    def periods_per_year_for_frequency(cls, frequency: str | None) -> int:
        normalized = (frequency or "").strip().lower()
        if normalized in {"d", "daily"} or "daily" in normalized:
            return cls._DAILY_PERIODS_PER_YEAR
        if normalized in {"w", "weekly"} or "weekly" in normalized:
            return 52
        if normalized in {"bw", "biweekly"} or "biweekly" in normalized:
            return 26
        if "semiannual" in normalized or "semi-annual" in normalized:
            return 2
        if normalized in {"q", "quarterly"} or "quarter" in normalized:
            return 4
        if normalized in {"a", "annual", "annually"} or "annual" in normalized or "year" in normalized:
            return 1
        return 12

    @staticmethod
    def _add_months(value: date, months: int) -> date:
        month_index = (value.month - 1) + months
        year = value.year + (month_index // 12)
        month = (month_index % 12) + 1
        if month == 2:
            leap_year = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
            max_day = 29 if leap_year else 28
        elif month in {4, 6, 9, 11}:
            max_day = 30
        else:
            max_day = 31
        return date(year, month, min(value.day, max_day))

    def subtract_periods(
        self,
        value: date,
        *,
        periods: int,
        frequency: str | None,
    ) -> date:
        if periods <= 0:
            return value

        normalized = (frequency or "").strip().lower()
        if normalized in {"d", "daily"} or "daily" in normalized:
            return value - timedelta(days=periods)
        if normalized in {"w", "weekly"} or "weekly" in normalized:
            return value - timedelta(days=periods * 7)
        if normalized in {"bw", "biweekly"} or "biweekly" in normalized:
            return value - timedelta(days=periods * 14)
        if "semiannual" in normalized or "semi-annual" in normalized:
            return self._add_months(value, -(periods * 6))
        if normalized in {"q", "quarterly"} or "quarter" in normalized:
            return self._add_months(value, -(periods * 3))
        if normalized in {"a", "annual", "annually"} or "annual" in normalized or "year" in normalized:
            try:
                return value.replace(year=value.year - periods)
            except ValueError:
                return value.replace(month=2, day=28, year=value.year - periods)
        return self._add_months(value, -periods)

    def default_window_for_transform(
        self,
        *,
        transform: TransformType,
        frequency: str | None,
    ) -> int | None:
        if transform not in (
            TransformType.ROLLING_AVERAGE,
            TransformType.ROLLING_STDDEV,
            TransformType.ROLLING_VOLATILITY,
        ):
            return None

        periods_per_year = self.periods_per_year_for_frequency(frequency)
        if periods_per_year >= self._DAILY_PERIODS_PER_YEAR:
            return 30
        if periods_per_year >= 52:
            return 13
        if periods_per_year >= 12:
            return 12
        if periods_per_year >= 4:
            return 4
        return 3

    def resolve_transform_window(
        self,
        *,
        transform: TransformType,
        frequency: str | None,
        requested_window: int | None,
    ) -> tuple[int | None, list[str]]:
        if requested_window is not None:
            return requested_window, []

        default_window = self.default_window_for_transform(transform=transform, frequency=frequency)
        if default_window is None:
            return None, []

        return (
            default_window,
            [f"Used a default {default_window}-observation rolling window because the query did not specify one."],
        )

    @staticmethod
    def transform_warmup_periods(
        *,
        transform: TransformType,
        periods_per_year: int,
        window: int | None,
    ) -> int:
        if transform == TransformType.PERIOD_OVER_PERIOD_PERCENT_CHANGE:
            return 1
        if transform == TransformType.YEAR_OVER_YEAR_PERCENT_CHANGE:
            return max(1, periods_per_year)
        if transform in (TransformType.ROLLING_AVERAGE, TransformType.ROLLING_STDDEV):
            return max(0, (window or 0) - 1)
        if transform == TransformType.ROLLING_VOLATILITY:
            return max(1, window or 0)
        return 0
