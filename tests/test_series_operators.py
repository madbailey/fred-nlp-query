from __future__ import annotations

from datetime import date, timedelta
import unittest

from fred_query.schemas.analysis import ObservationPoint, SeriesAnalysis
from fred_query.schemas.intent import QueryIntent, TaskType, TransformType
from fred_query.schemas.resolved_series import ResolvedSeries, SeriesMetadata
from fred_query.services.operators import (
    ApplyTransformOp,
    FetchSeriesObservationsOp,
    RankSeriesOp,
    ResolveSeriesOp,
)
from fred_query.services.resolver_service import ResolverService
from fred_query.services.transform_service import TransformService


class _OperatorFREDClient:
    def __init__(self) -> None:
        self.base_date = date(1970, 1, 1)

    def get_series_metadata(self, series_id: str) -> SeriesMetadata:
        if series_id == "SP500":
            return SeriesMetadata(
                series_id=series_id,
                title="S&P 500",
                units="Index",
                frequency="Daily",
                seasonal_adjustment="NSA",
                source_url=f"https://fred.stlouisfed.org/series/{series_id}",
            )
        return SeriesMetadata(
            series_id=series_id,
            title="Unemployment Rate",
            units="Percent",
            frequency="Monthly",
            seasonal_adjustment="SA",
            source_url=f"https://fred.stlouisfed.org/series/{series_id}",
        )

    def _value_for_date(self, current_date: date) -> float:
        offset = (current_date - self.base_date).days
        return 1000.0 + (offset * 0.25) + ((offset % 7) * 4.0)

    def get_series_observations(
        self,
        series_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
        *,
        frequency: str | None = None,
        aggregation_method: str | None = None,
        limit: int | None = None,
        sort_order: str | None = None,
    ) -> list[ObservationPoint]:
        if series_id != "SP500":
            return [
                ObservationPoint(date=date(2024, 1, 1), value=3.9),
                ObservationPoint(date=date(2024, 2, 1), value=4.0),
            ]

        current_date = start_date or date(2024, 1, 1)
        final_date = end_date or date(2024, 2, 15)
        observations: list[ObservationPoint] = []
        while current_date <= final_date:
            observations.append(ObservationPoint(date=current_date, value=self._value_for_date(current_date)))
            current_date += timedelta(days=1)
        return observations


class SeriesOperatorsTest(unittest.TestCase):
    def test_resolve_series_op_uses_resolver_service_for_explicit_series_id(self) -> None:
        resolver = ResolverService(_OperatorFREDClient())
        op = ResolveSeriesOp(resolver)
        intent = QueryIntent(task_type=TaskType.SINGLE_SERIES_LOOKUP, series_id="UNRATE")

        result = op.for_single_series(intent)

        self.assertEqual(result.metadata.series_id, "UNRATE")
        self.assertEqual(result.resolved_series.series_id, "UNRATE")
        self.assertIsNone(result.search_match)

    def test_fetch_observations_op_delegates_required_observation_fetch(self) -> None:
        resolver = ResolverService(_OperatorFREDClient())
        op = FetchSeriesObservationsOp(resolver)

        observations = op.fetch("UNRATE", start_date=date(2024, 1, 1), end_date=date(2024, 2, 1))

        self.assertEqual([point.date for point in observations], [date(2024, 1, 1), date(2024, 2, 1)])

    def test_apply_transform_op_plans_warmup_and_applies_visible_transform(self) -> None:
        transform_service = TransformService()
        op = ApplyTransformOp(transform_service)
        metadata = SeriesMetadata(
            series_id="SP500",
            title="S&P 500",
            units="Index",
            frequency="Daily",
            seasonal_adjustment="NSA",
            source_url="https://fred.stlouisfed.org/series/SP500",
        )
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            series_id="SP500",
            start_date=date(2024, 2, 1),
            transform=TransformType.ROLLING_VOLATILITY,
        )

        plan = op.plan_single_series(
            intent,
            metadata=metadata,
            start_date=date(2024, 2, 1),
            end_date=None,
        )
        observations = _OperatorFREDClient().get_series_observations("SP500", start_date=plan.fetch_start_date)
        result = op.apply_single_series(observations, metadata=metadata, plan=plan)

        self.assertEqual(plan.transform_window, 30)
        self.assertEqual(plan.fetch_start_date, date(2024, 1, 2))
        self.assertEqual(result.analysis_basis, "30-observation rolling annualized volatility")
        self.assertEqual(result.transformed_observations[0].date, date(2024, 2, 1))

    def test_rank_series_op_orders_by_latest_value(self) -> None:
        first = SeriesAnalysis(
            series=ResolvedSeries(
                series_id="A",
                title="A",
                geography="A",
                indicator="test",
                units="Percent",
                frequency="M",
                resolution_reason="fixture",
                source_url="https://fred.stlouisfed.org/series/A",
            ),
            latest_value=1.0,
        )
        second = first.model_copy(
            update={
                "series": first.series.model_copy(update={"series_id": "B", "title": "B"}),
                "latest_value": 2.0,
            }
        )

        ranked = RankSeriesOp.rank([first, second], descending=True)

        self.assertEqual([item.series.series_id for item in ranked], ["B", "A"])


if __name__ == "__main__":
    unittest.main()
