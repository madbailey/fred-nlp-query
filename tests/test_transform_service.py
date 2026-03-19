from __future__ import annotations

from datetime import date
import unittest

from fred_query.schemas.analysis import ObservationPoint
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


if __name__ == "__main__":
    unittest.main()
