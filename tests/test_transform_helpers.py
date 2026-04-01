from __future__ import annotations

from datetime import date
import unittest

from fred_query.schemas.analysis import ObservationPoint
from fred_query.schemas.intent import TransformType
from fred_query.services.transform.relationship import RelationshipTransformService
from fred_query.services.transform.series_stats import SeriesStatisticsService


class RelationshipTransformServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RelationshipTransformService()

    def test_build_relationship_basis_keeps_reported_levels_for_rate_series(self) -> None:
        observations = [
            ObservationPoint(date=date(2024, month, 1), value=4.0 + month)
            for month in range(1, 4)
        ]

        transformed, basis, units, window, warnings = self.service.build_relationship_basis(
            observations,
            title="Unemployment Rate",
            units="Percent",
            frequency="Monthly",
            periods_per_year=12,
            transform=TransformType.LEVEL,
        )

        self.assertEqual(transformed, observations)
        self.assertEqual(basis, "Reported level")
        self.assertEqual(units, "Percent")
        self.assertIsNone(window)
        self.assertEqual(warnings, [])


class SeriesStatisticsServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = SeriesStatisticsService()

    def test_derive_recession_periods_splits_discontinuous_runs(self) -> None:
        observations = [
            ObservationPoint(date=date(2020, 1, 1), value=1.0),
            ObservationPoint(date=date(2020, 2, 1), value=1.0),
            ObservationPoint(date=date(2020, 6, 1), value=1.0),
            ObservationPoint(date=date(2020, 7, 1), value=1.0),
        ]

        periods = self.service.derive_recession_periods(observations)

        self.assertEqual(len(periods), 2)
        self.assertEqual(periods[0].start_date, date(2020, 1, 1))
        self.assertEqual(periods[0].end_date, date(2020, 2, 1))
        self.assertEqual(periods[1].start_date, date(2020, 6, 1))
        self.assertEqual(periods[1].end_date, date(2020, 7, 1))


if __name__ == "__main__":
    unittest.main()
