from __future__ import annotations

from datetime import date
import unittest

from fred_query.schemas.analysis import ObservationPoint
from fred_query.schemas.intent import TransformType
from fred_query.services.transform_service import TransformService


class TransformServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = TransformService()

    def test_normalize_to_index(self) -> None:
        observations = [
            ObservationPoint(date=date(2010, 1, 1), value=100.0),
            ObservationPoint(date=date(2011, 1, 1), value=125.0),
            ObservationPoint(date=date(2012, 1, 1), value=150.0),
        ]

        normalized = self.service.normalize_to_index(observations)

        self.assertEqual([round(point.value, 2) for point in normalized], [100.0, 125.0, 150.0])

    def test_growth_metrics(self) -> None:
        observations = [
            ObservationPoint(date=date(2010, 1, 1), value=100.0),
            ObservationPoint(date=date(2012, 1, 1), value=121.0),
        ]

        total_growth = self.service.calculate_total_growth_pct(observations)
        cagr = self.service.calculate_cagr_pct(observations)

        self.assertAlmostEqual(total_growth or 0.0, 21.0, places=4)
        self.assertAlmostEqual(cagr or 0.0, 10.0, places=1)

    def test_summarize_historical_context(self) -> None:
        observations = [
            ObservationPoint(date=date(1974, 1, 1), value=8.0),
            ObservationPoint(date=date(1990, 1, 1), value=6.5),
            ObservationPoint(date=date(2000, 1, 1), value=5.5),
            ObservationPoint(date=date(2010, 1, 1), value=9.0),
            ObservationPoint(date=date(2020, 1, 1), value=14.7),
            ObservationPoint(date=date(2024, 1, 1), value=4.1),
        ]

        context = self.service.summarize_historical_context(observations)

        self.assertIsNotNone(context)
        self.assertEqual(context.start_date, date(1974, 1, 1))
        self.assertEqual(context.end_date, date(2024, 1, 1))
        self.assertEqual(context.observation_count, 6)
        self.assertAlmostEqual(context.average_value or 0.0, 7.9667, places=4)
        self.assertAlmostEqual(context.percentile_rank or 0.0, 16.6667, places=4)
        self.assertEqual(context.max_value, 14.7)
        self.assertEqual(context.max_date, date(2020, 1, 1))
        self.assertEqual(context.min_value, 4.1)
        self.assertEqual(context.min_date, date(2024, 1, 1))

    def test_apply_single_series_transform_supports_year_over_year_change(self) -> None:
        observations = [
            ObservationPoint(date=date(2020 + (month - 1) // 12, ((month - 1) % 12) + 1, 1), value=100.0)
            for month in range(1, 13)
        ] + [
            ObservationPoint(date=date(2021 + (month - 1) // 12, ((month - 1) % 12) + 1, 1), value=110.0)
            for month in range(1, 13)
        ]

        transformed = self.service.apply_single_series_transform(
            observations,
            transform=TransformType.YEAR_OVER_YEAR_PERCENT_CHANGE,
            units="Index",
            frequency="Monthly",
        )

        self.assertEqual(transformed.basis, "Year-over-year percent change")
        self.assertEqual(transformed.units, "Percent")
        self.assertEqual(len(transformed.observations or []), 12)
        self.assertTrue(all(round(point.value, 2) == 10.0 for point in transformed.observations or []))

    def test_rolling_helpers_and_defaults(self) -> None:
        observations = [
            ObservationPoint(date=date(2024, 1, day), value=float(day))
            for day in range(1, 6)
        ]

        rolling_average = self.service.rolling_average(observations, window=3)
        rolling_stddev = self.service.rolling_stddev(observations, window=3)
        default_window, warnings = self.service.resolve_transform_window(
            transform=TransformType.ROLLING_VOLATILITY,
            frequency="Daily",
            requested_window=None,
        )

        self.assertEqual([round(point.value, 2) for point in rolling_average], [2.0, 3.0, 4.0])
        self.assertEqual([round(point.value, 4) for point in rolling_stddev], [1.0, 1.0, 1.0])
        self.assertEqual(default_window, 30)
        self.assertIn("30-observation rolling window", warnings[0])

    def test_relationship_helpers(self) -> None:
        code, label, periods_per_year, lag_unit = self.service.choose_relationship_frequency(["Daily", "Monthly"])

        self.assertEqual(code, "m")
        self.assertEqual(label, "Monthly")
        self.assertEqual(periods_per_year, 12)
        self.assertEqual(lag_unit, "months")

    def test_pct_change_alignment_and_correlation(self) -> None:
        first = [
            ObservationPoint(date=date(2020, month, 1), value=float(month))
            for month in range(1, 13)
        ]
        second = [
            ObservationPoint(date=date(2020, month, 1), value=float(month * 2))
            for month in range(1, 13)
        ]

        aligned_first, aligned_second = self.service.align_on_dates(first, second)
        correlation = self.service.calculate_correlation(aligned_first, aligned_second)
        slope = self.service.calculate_regression_slope(aligned_first, aligned_second)

        self.assertEqual(len(aligned_first), 12)
        self.assertAlmostEqual(correlation or 0.0, 1.0, places=6)
        self.assertAlmostEqual(slope or 0.0, 2.0, places=6)

    def test_best_lag_correlation_finds_lead(self) -> None:
        first = [
            ObservationPoint(date=date(2020, month, 1), value=float(month))
            for month in range(1, 13)
        ]
        second_values = [99.0] + [float(month) for month in range(1, 12)]
        second = [
            ObservationPoint(date=date(2020, month, 1), value=second_values[month - 1])
            for month in range(1, 13)
        ]

        lag, correlation, sample_size = self.service.calculate_best_lag_correlation(first, second, max_lag=2)

        self.assertEqual(lag, 1)
        self.assertAlmostEqual(correlation or 0.0, 1.0, places=6)
        self.assertGreaterEqual(sample_size, 8)


if __name__ == "__main__":
    unittest.main()
