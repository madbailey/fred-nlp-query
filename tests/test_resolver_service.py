from __future__ import annotations

import unittest

from fred_query.schemas.resolved_series import SeriesMetadata, SeriesSearchMatch
from fred_query.services.resolver_service import ResolverService


class _RankingFREDClient:
    def __init__(self) -> None:
        self.last_search_limit: int | None = None
        self.metadata = {
            "T10YIE": SeriesMetadata(
                series_id="T10YIE",
                title="10-Year Breakeven Inflation Rate",
                units="Percent",
                frequency="Daily",
                source_url="https://fred.stlouisfed.org/series/T10YIE",
            ),
            "PCEPI": SeriesMetadata(
                series_id="PCEPI",
                title="Personal Consumption Expenditures: Chain-type Price Index",
                units="Index 2017=100",
                frequency="Monthly",
                source_url="https://fred.stlouisfed.org/series/PCEPI",
            ),
            "CPIAUCSL": SeriesMetadata(
                series_id="CPIAUCSL",
                title="Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
                units="Index 1982-1984=100",
                frequency="Monthly",
                source_url="https://fred.stlouisfed.org/series/CPIAUCSL",
            ),
            "GDP": SeriesMetadata(
                series_id="GDP",
                title="Gross Domestic Product",
                units="Billions of Current Dollars",
                frequency="Quarterly",
                seasonal_adjustment="SAAR",
                source_url="https://fred.stlouisfed.org/series/GDP",
            ),
            "A191RL1Q225SBEA": SeriesMetadata(
                series_id="A191RL1Q225SBEA",
                title="Real Gross Domestic Product",
                units="Percent Change from Preceding Period",
                frequency="Quarterly",
                seasonal_adjustment="SAAR",
                source_url="https://fred.stlouisfed.org/series/A191RL1Q225SBEA",
            ),
            "GDPC1": SeriesMetadata(
                series_id="GDPC1",
                title="Real Gross Domestic Product",
                units="Billions of Chained 2017 Dollars",
                frequency="Quarterly",
                seasonal_adjustment="SAAR",
                source_url="https://fred.stlouisfed.org/series/GDPC1",
            ),
            "UNRATE": SeriesMetadata(
                series_id="UNRATE",
                title="Unemployment Rate",
                units="Percent",
                frequency="Monthly",
                seasonal_adjustment="Seasonally Adjusted",
                source_url="https://fred.stlouisfed.org/series/UNRATE",
            ),
            "TXURN": SeriesMetadata(
                series_id="TXURN",
                title="Unemployment Rate in Texas",
                units="Percent",
                frequency="Monthly",
                seasonal_adjustment="Seasonally Adjusted",
                source_url="https://fred.stlouisfed.org/series/TXURN",
            ),
        }

    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        self.last_search_limit = limit
        lowered = search_text.lower()
        if "inflation" in lowered:
            return [
                SeriesSearchMatch(
                    series_id="T10YIE",
                    title=self.metadata["T10YIE"].title,
                    units=self.metadata["T10YIE"].units,
                    frequency=self.metadata["T10YIE"].frequency,
                    popularity=100,
                    source_url=self.metadata["T10YIE"].source_url,
                ),
                SeriesSearchMatch(
                    series_id="PCEPI",
                    title=self.metadata["PCEPI"].title,
                    units=self.metadata["PCEPI"].units,
                    frequency=self.metadata["PCEPI"].frequency,
                    popularity=88,
                    source_url=self.metadata["PCEPI"].source_url,
                ),
                SeriesSearchMatch(
                    series_id="CPIAUCSL",
                    title=self.metadata["CPIAUCSL"].title,
                    units=self.metadata["CPIAUCSL"].units,
                    frequency=self.metadata["CPIAUCSL"].frequency,
                    popularity=95,
                    source_url=self.metadata["CPIAUCSL"].source_url,
                ),
            ]
        if "gdp" in lowered:
            return [
                SeriesSearchMatch(
                    series_id="GDP",
                    title=self.metadata["GDP"].title,
                    units=self.metadata["GDP"].units,
                    frequency=self.metadata["GDP"].frequency,
                    seasonal_adjustment=self.metadata["GDP"].seasonal_adjustment,
                    popularity=94,
                    source_url=self.metadata["GDP"].source_url,
                ),
                SeriesSearchMatch(
                    series_id="A191RL1Q225SBEA",
                    title=self.metadata["A191RL1Q225SBEA"].title,
                    units=self.metadata["A191RL1Q225SBEA"].units,
                    frequency=self.metadata["A191RL1Q225SBEA"].frequency,
                    seasonal_adjustment=self.metadata["A191RL1Q225SBEA"].seasonal_adjustment,
                    popularity=78,
                    source_url=self.metadata["A191RL1Q225SBEA"].source_url,
                ),
                SeriesSearchMatch(
                    series_id="GDPC1",
                    title=self.metadata["GDPC1"].title,
                    units=self.metadata["GDPC1"].units,
                    frequency=self.metadata["GDPC1"].frequency,
                    seasonal_adjustment=self.metadata["GDPC1"].seasonal_adjustment,
                    popularity=91,
                    source_url=self.metadata["GDPC1"].source_url,
                ),
            ]
        return [
            SeriesSearchMatch(
                series_id="UNRATE",
                title=self.metadata["UNRATE"].title,
                units=self.metadata["UNRATE"].units,
                frequency=self.metadata["UNRATE"].frequency,
                seasonal_adjustment=self.metadata["UNRATE"].seasonal_adjustment,
                popularity=95,
                source_url=self.metadata["UNRATE"].source_url,
            ),
            SeriesSearchMatch(
                series_id="TXURN",
                title=self.metadata["TXURN"].title,
                units=self.metadata["TXURN"].units,
                frequency=self.metadata["TXURN"].frequency,
                seasonal_adjustment=self.metadata["TXURN"].seasonal_adjustment,
                popularity=72,
                source_url=self.metadata["TXURN"].source_url,
            ),
        ]

    def get_series_metadata(self, series_id: str) -> SeriesMetadata:
        return self.metadata[series_id]


class _ConfidenceBandFREDClient:
    def __init__(self) -> None:
        self.metadata = {
            "WINNER": SeriesMetadata(
                series_id="WINNER",
                title="Winner Series",
                units="Index",
                frequency="Monthly",
                source_url="https://fred.stlouisfed.org/series/WINNER",
            ),
            "RUNNERUP": SeriesMetadata(
                series_id="RUNNERUP",
                title="Runner-up Series",
                units="Index",
                frequency="Monthly",
                source_url="https://fred.stlouisfed.org/series/RUNNERUP",
            ),
        }

    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        return [
            SeriesSearchMatch(
                series_id="WINNER",
                title=self.metadata["WINNER"].title,
                units=self.metadata["WINNER"].units,
                frequency=self.metadata["WINNER"].frequency,
                source_url=self.metadata["WINNER"].source_url,
            ),
            SeriesSearchMatch(
                series_id="RUNNERUP",
                title=self.metadata["RUNNERUP"].title,
                units=self.metadata["RUNNERUP"].units,
                frequency=self.metadata["RUNNERUP"].frequency,
                source_url=self.metadata["RUNNERUP"].source_url,
            ),
        ]

    def get_series_metadata(self, series_id: str) -> SeriesMetadata:
        return self.metadata[series_id]


class ResolverServiceTest(unittest.TestCase):
    def test_resolve_series_reranks_plain_inflation_queries_away_from_market_based_first_hit(self) -> None:
        client = _RankingFREDClient()
        resolver = ResolverService(client)

        resolved, metadata, search_match = resolver.resolve_series(
            search_text="inflation united states",
            geography="United States",
            indicator="inflation",
        )

        self.assertEqual(client.last_search_limit, 15)
        self.assertEqual(metadata.series_id, "CPIAUCSL")
        self.assertEqual(search_match.series_id, "CPIAUCSL")
        self.assertEqual(resolved.series_id, "CPIAUCSL")
        self.assertIn("reranked FRED search candidates", resolved.resolution_reason)

    def test_resolve_series_prefers_real_level_series_over_nominal_or_growth_first_hits(self) -> None:
        client = _RankingFREDClient()
        resolver = ResolverService(client)

        resolved, metadata, search_match = resolver.resolve_series(
            search_text="real gdp united states",
            geography="United States",
            indicator="real gdp",
        )

        self.assertEqual(metadata.series_id, "GDPC1")
        self.assertEqual(search_match.series_id, "GDPC1")
        self.assertEqual(resolved.series_id, "GDPC1")

    def test_resolve_series_uses_geography_signal_in_reranking(self) -> None:
        client = _RankingFREDClient()
        resolver = ResolverService(client)

        resolved, metadata, search_match = resolver.resolve_series(
            search_text="texas unemployment rate",
            geography="Texas",
            indicator="unemployment rate",
        )

        self.assertEqual(metadata.series_id, "TXURN")
        self.assertEqual(search_match.series_id, "TXURN")
        self.assertEqual(resolved.geography, "Texas")

    def test_confidence_from_rank_gap_uses_close_call_band(self) -> None:
        confidence = ResolverService._confidence_from_rank_gap(
            [
                (10.0, SeriesSearchMatch(series_id="WINNER", title="Winner", source_url="https://fred.stlouisfed.org/series/WINNER")),
                (8.5, SeriesSearchMatch(series_id="RUNNERUP", title="Runner-up", source_url="https://fred.stlouisfed.org/series/RUNNERUP")),
            ]
        )

        self.assertEqual(confidence, 0.6)

    def test_confidence_from_rank_gap_uses_clear_gap_band(self) -> None:
        confidence = ResolverService._confidence_from_rank_gap(
            [
                (12.0, SeriesSearchMatch(series_id="WINNER", title="Winner", source_url="https://fred.stlouisfed.org/series/WINNER")),
                (6.0, SeriesSearchMatch(series_id="RUNNERUP", title="Runner-up", source_url="https://fred.stlouisfed.org/series/RUNNERUP")),
            ]
        )

        self.assertEqual(confidence, 0.92)

    def test_resolve_series_uses_rank_gap_confidence_instead_of_absolute_score_scaling(self) -> None:
        client = _ConfidenceBandFREDClient()
        resolver = ResolverService(client)

        resolver._rank_search_matches = lambda **_: [  # type: ignore[method-assign]
            (11.0, SeriesSearchMatch(series_id="WINNER", title="Winner Series", source_url="https://fred.stlouisfed.org/series/WINNER")),
            (8.2, SeriesSearchMatch(series_id="RUNNERUP", title="Runner-up Series", source_url="https://fred.stlouisfed.org/series/RUNNERUP")),
        ]

        resolved, metadata, _ = resolver.resolve_series(
            search_text="winner query",
            geography="United States",
            indicator="winner",
        )

        self.assertEqual(metadata.series_id, "WINNER")
        self.assertEqual(resolved.score, 0.78)


if __name__ == "__main__":
    unittest.main()
