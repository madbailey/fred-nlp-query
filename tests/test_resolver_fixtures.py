"""Deterministic resolver fixture suite (EVAL-002).

Covers ambiguity, geography hints, units/frequency preferences, and
top-hit reranking without touching live FRED or OpenAI endpoints.
"""

from __future__ import annotations

import unittest

from fred_query.schemas.resolved_series import SeriesMetadata, SeriesSearchMatch
from fred_query.services.resolver_service import ResolverService


# ---------------------------------------------------------------------------
# Shared mock FRED clients
# ---------------------------------------------------------------------------

class _AmbiguityFREDClient:
    """Two candidates with a small score gap — resolver should still pick the
    better match but report a low-confidence (close-call) score."""

    def __init__(self) -> None:
        self.metadata = {
            "FEDFUNDS": SeriesMetadata(
                series_id="FEDFUNDS",
                title="Federal Funds Effective Rate",
                units="Percent",
                frequency="Monthly",
                seasonal_adjustment="Not Seasonally Adjusted",
                source_url="https://fred.stlouisfed.org/series/FEDFUNDS",
            ),
            "DFF": SeriesMetadata(
                series_id="DFF",
                title="Federal Funds Effective Rate",
                units="Percent",
                frequency="Daily",
                seasonal_adjustment="Not Seasonally Adjusted",
                source_url="https://fred.stlouisfed.org/series/DFF",
            ),
        }

    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        return [
            SeriesSearchMatch(
                series_id="FEDFUNDS",
                title=self.metadata["FEDFUNDS"].title,
                units=self.metadata["FEDFUNDS"].units,
                frequency=self.metadata["FEDFUNDS"].frequency,
                seasonal_adjustment=self.metadata["FEDFUNDS"].seasonal_adjustment,
                popularity=95,
                source_url=self.metadata["FEDFUNDS"].source_url,
            ),
            SeriesSearchMatch(
                series_id="DFF",
                title=self.metadata["DFF"].title,
                units=self.metadata["DFF"].units,
                frequency=self.metadata["DFF"].frequency,
                seasonal_adjustment=self.metadata["DFF"].seasonal_adjustment,
                popularity=92,
                source_url=self.metadata["DFF"].source_url,
            ),
        ]

    def get_series_metadata(self, series_id: str) -> SeriesMetadata:
        return self.metadata[series_id]


class _GeographyHintFREDClient:
    """State-level and national candidates — geography signal should decide."""

    def __init__(self) -> None:
        self.metadata = {
            "UNRATE": SeriesMetadata(
                series_id="UNRATE",
                title="Unemployment Rate",
                units="Percent",
                frequency="Monthly",
                seasonal_adjustment="Seasonally Adjusted",
                source_url="https://fred.stlouisfed.org/series/UNRATE",
            ),
            "CAUR": SeriesMetadata(
                series_id="CAUR",
                title="Unemployment Rate in California",
                units="Percent",
                frequency="Monthly",
                seasonal_adjustment="Seasonally Adjusted",
                source_url="https://fred.stlouisfed.org/series/CAUR",
            ),
            "NYUR": SeriesMetadata(
                series_id="NYUR",
                title="Unemployment Rate in New York",
                units="Percent",
                frequency="Monthly",
                seasonal_adjustment="Seasonally Adjusted",
                source_url="https://fred.stlouisfed.org/series/NYUR",
            ),
            "FLUR": SeriesMetadata(
                series_id="FLUR",
                title="Unemployment Rate in Florida",
                units="Percent",
                frequency="Monthly",
                seasonal_adjustment="Seasonally Adjusted",
                source_url="https://fred.stlouisfed.org/series/FLUR",
            ),
        }

    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        lowered = search_text.lower()
        if "california" in lowered:
            return [
                self._match("UNRATE"),
                self._match("CAUR"),
                self._match("NYUR"),
            ]
        if "new york" in lowered:
            return [
                self._match("UNRATE"),
                self._match("NYUR"),
                self._match("CAUR"),
            ]
        if "florida" in lowered:
            return [
                self._match("UNRATE"),
                self._match("FLUR"),
                self._match("CAUR"),
            ]
        return [self._match("UNRATE")]

    def _match(self, series_id: str) -> SeriesSearchMatch:
        m = self.metadata[series_id]
        return SeriesSearchMatch(
            series_id=m.series_id,
            title=m.title,
            units=m.units,
            frequency=m.frequency,
            seasonal_adjustment=m.seasonal_adjustment,
            popularity=90,
            source_url=m.source_url,
        )

    def get_series_metadata(self, series_id: str) -> SeriesMetadata:
        return self.metadata[series_id]


class _FrequencyPreferenceFREDClient:
    """Monthly vs quarterly GDP candidates — frequency hint should decide."""

    def __init__(self) -> None:
        self.metadata = {
            "GDP": SeriesMetadata(
                series_id="GDP",
                title="Gross Domestic Product",
                units="Billions of Dollars",
                frequency="Quarterly",
                seasonal_adjustment="SAAR",
                source_url="https://fred.stlouisfed.org/series/GDP",
            ),
            "GDPC1": SeriesMetadata(
                series_id="GDPC1",
                title="Real Gross Domestic Product",
                units="Billions of Chained 2017 Dollars",
                frequency="Quarterly",
                seasonal_adjustment="SAAR",
                source_url="https://fred.stlouisfed.org/series/GDPC1",
            ),
            "PCEPILFE": SeriesMetadata(
                series_id="PCEPILFE",
                title="Personal Consumption Expenditures Excluding Food and Energy (Chain-Type Price Index)",
                units="Index 2017=100",
                frequency="Monthly",
                seasonal_adjustment="Seasonally Adjusted",
                source_url="https://fred.stlouisfed.org/series/PCEPILFE",
            ),
        }

    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        lowered = search_text.lower()
        if "monthly" in lowered or "core pce" in lowered:
            return [
                self._match("GDP"),
                self._match("PCEPILFE"),
            ]
        return [
            self._match("GDP"),
            self._match("GDPC1"),
        ]

    def _match(self, series_id: str) -> SeriesSearchMatch:
        m = self.metadata[series_id]
        return SeriesSearchMatch(
            series_id=m.series_id,
            title=m.title,
            units=m.units,
            frequency=m.frequency,
            seasonal_adjustment=m.seasonal_adjustment,
            popularity=85,
            source_url=m.source_url,
        )

    def get_series_metadata(self, series_id: str) -> SeriesMetadata:
        return self.metadata[series_id]


class _TopHitMistakeFREDClient:
    """FRED search returns a market-instrument series as hit #1, but the user
    wants the consumer-facing headline index.  The reranker should fix this."""

    def __init__(self) -> None:
        self.metadata = {
            "T5YIE": SeriesMetadata(
                series_id="T5YIE",
                title="5-Year Breakeven Inflation Rate",
                units="Percent",
                frequency="Daily",
                source_url="https://fred.stlouisfed.org/series/T5YIE",
            ),
            "CPIAUCSL": SeriesMetadata(
                series_id="CPIAUCSL",
                title="Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
                units="Index 1982-1984=100",
                frequency="Monthly",
                source_url="https://fred.stlouisfed.org/series/CPIAUCSL",
            ),
            "PCEPI": SeriesMetadata(
                series_id="PCEPI",
                title="Personal Consumption Expenditures: Chain-type Price Index",
                units="Index 2017=100",
                frequency="Monthly",
                source_url="https://fred.stlouisfed.org/series/PCEPI",
            ),
        }

    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        return [
            SeriesSearchMatch(
                series_id="T5YIE",
                title=self.metadata["T5YIE"].title,
                units=self.metadata["T5YIE"].units,
                frequency=self.metadata["T5YIE"].frequency,
                popularity=100,
                source_url=self.metadata["T5YIE"].source_url,
            ),
            SeriesSearchMatch(
                series_id="CPIAUCSL",
                title=self.metadata["CPIAUCSL"].title,
                units=self.metadata["CPIAUCSL"].units,
                frequency=self.metadata["CPIAUCSL"].frequency,
                popularity=95,
                source_url=self.metadata["CPIAUCSL"].source_url,
            ),
            SeriesSearchMatch(
                series_id="PCEPI",
                title=self.metadata["PCEPI"].title,
                units=self.metadata["PCEPI"].units,
                frequency=self.metadata["PCEPI"].frequency,
                popularity=88,
                source_url=self.metadata["PCEPI"].source_url,
            ),
        ]

    def get_series_metadata(self, series_id: str) -> SeriesMetadata:
        return self.metadata[series_id]


class _UnitsPreferenceFREDClient:
    """Real vs nominal GDP — 'real gdp' query should prefer chained dollars."""

    def __init__(self) -> None:
        self.metadata = {
            "GDP": SeriesMetadata(
                series_id="GDP",
                title="Gross Domestic Product",
                units="Billions of Current Dollars",
                frequency="Quarterly",
                seasonal_adjustment="SAAR",
                source_url="https://fred.stlouisfed.org/series/GDP",
            ),
            "GDPC1": SeriesMetadata(
                series_id="GDPC1",
                title="Real Gross Domestic Product",
                units="Billions of Chained 2017 Dollars",
                frequency="Quarterly",
                seasonal_adjustment="SAAR",
                source_url="https://fred.stlouisfed.org/series/GDPC1",
            ),
            "A191RL1Q225SBEA": SeriesMetadata(
                series_id="A191RL1Q225SBEA",
                title="Real Gross Domestic Product",
                units="Percent Change from Preceding Period",
                frequency="Quarterly",
                seasonal_adjustment="SAAR",
                source_url="https://fred.stlouisfed.org/series/A191RL1Q225SBEA",
            ),
        }

    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        return [
            self._match("GDP", popularity=94),
            self._match("A191RL1Q225SBEA", popularity=78),
            self._match("GDPC1", popularity=91),
        ]

    def _match(self, series_id: str, *, popularity: int = 80) -> SeriesSearchMatch:
        m = self.metadata[series_id]
        return SeriesSearchMatch(
            series_id=m.series_id,
            title=m.title,
            units=m.units,
            frequency=m.frequency,
            seasonal_adjustment=m.seasonal_adjustment,
            popularity=popularity,
            source_url=m.source_url,
        )

    def get_series_metadata(self, series_id: str) -> SeriesMetadata:
        return self.metadata[series_id]


class _StateGDPResolutionFREDClient:
    """Supports deterministic state GDP series pattern resolution."""

    def __init__(self) -> None:
        self.metadata = {
            "CARGSP": SeriesMetadata(
                series_id="CARGSP",
                title="Real Gross Domestic Product: All Industries in California",
                units="Millions of Chained 2017 Dollars",
                frequency="Annual",
                source_url="https://fred.stlouisfed.org/series/CARGSP",
            ),
            "TXRGSP": SeriesMetadata(
                series_id="TXRGSP",
                title="Real Gross Domestic Product: All Industries in Texas",
                units="Millions of Chained 2017 Dollars",
                frequency="Annual",
                source_url="https://fred.stlouisfed.org/series/TXRGSP",
            ),
        }

    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        return []

    def get_series_metadata(self, series_id: str) -> SeriesMetadata:
        return self.metadata[series_id]


# ---------------------------------------------------------------------------
# Fixture suite: ambiguity
# ---------------------------------------------------------------------------

class ResolverAmbiguityFixtures(unittest.TestCase):
    """Close-call scenarios where two candidates are nearly equivalent."""

    def test_close_candidates_still_pick_winner_and_report_close_call_confidence(self) -> None:
        client = _AmbiguityFREDClient()
        resolver = ResolverService(client)

        resolved, metadata, _ = resolver.resolve_series(
            search_text="federal funds rate",
            geography="United States",
            indicator="federal funds rate",
        )

        self.assertIn(resolved.series_id, {"FEDFUNDS", "DFF"})
        self.assertEqual(resolved.score, 0.6, "close-call gap should yield 0.6 confidence")

    def test_single_candidate_returns_single_candidate_confidence_band(self) -> None:
        confidence = ResolverService._confidence_from_rank_gap(
            [
                (10.0, SeriesSearchMatch(
                    series_id="ONLY",
                    title="Only Match",
                    source_url="https://fred.stlouisfed.org/series/ONLY",
                )),
            ]
        )

        self.assertEqual(confidence, 0.72)

    def test_moderate_gap_returns_moderate_confidence_band(self) -> None:
        confidence = ResolverService._confidence_from_rank_gap(
            [
                (10.0, SeriesSearchMatch(
                    series_id="W",
                    title="Winner",
                    source_url="https://fred.stlouisfed.org/series/W",
                )),
                (7.5, SeriesSearchMatch(
                    series_id="R",
                    title="Runner-up",
                    source_url="https://fred.stlouisfed.org/series/R",
                )),
            ]
        )

        self.assertEqual(confidence, 0.78)


# ---------------------------------------------------------------------------
# Fixture suite: geography hints
# ---------------------------------------------------------------------------

class ResolverGeographyFixtures(unittest.TestCase):
    """Geography signals should steer ranking toward the matching region."""

    def test_california_geography_picks_california_series(self) -> None:
        client = _GeographyHintFREDClient()
        resolver = ResolverService(client)

        resolved, metadata, _ = resolver.resolve_series(
            search_text="unemployment rate california",
            geography="California",
            indicator="unemployment rate",
        )

        self.assertEqual(resolved.series_id, "CAUR")
        self.assertEqual(resolved.geography, "California")

    def test_new_york_geography_picks_new_york_series(self) -> None:
        client = _GeographyHintFREDClient()
        resolver = ResolverService(client)

        resolved, metadata, _ = resolver.resolve_series(
            search_text="unemployment rate new york",
            geography="New York",
            indicator="unemployment rate",
        )

        self.assertEqual(resolved.series_id, "NYUR")
        self.assertEqual(resolved.geography, "New York")

    def test_florida_geography_picks_florida_series(self) -> None:
        client = _GeographyHintFREDClient()
        resolver = ResolverService(client)

        resolved, metadata, _ = resolver.resolve_series(
            search_text="unemployment rate florida",
            geography="Florida",
            indicator="unemployment rate",
        )

        self.assertEqual(resolved.series_id, "FLUR")
        self.assertEqual(resolved.geography, "Florida")

    def test_state_gdp_deterministic_pattern_resolves_california(self) -> None:
        client = _StateGDPResolutionFREDClient()
        resolver = ResolverService(client)

        resolved = resolver.resolve_state_gdp_series("California")

        self.assertEqual(resolved.series_id, "CARGSP")
        self.assertEqual(resolved.geography, "California")
        self.assertIn("CARGSP", resolved.resolution_reason)

    def test_state_gdp_deterministic_pattern_resolves_texas(self) -> None:
        client = _StateGDPResolutionFREDClient()
        resolver = ResolverService(client)

        resolved = resolver.resolve_state_gdp_series("Texas")

        self.assertEqual(resolved.series_id, "TXRGSP")
        self.assertEqual(resolved.geography, "Texas")
        self.assertIn("TXRGSP", resolved.resolution_reason)


# ---------------------------------------------------------------------------
# Fixture suite: units and frequency preferences
# ---------------------------------------------------------------------------

class ResolverUnitsFrequencyFixtures(unittest.TestCase):
    """Unit and frequency signals should influence ranking."""

    def test_real_gdp_query_prefers_chained_dollar_level_series_over_nominal(self) -> None:
        client = _UnitsPreferenceFREDClient()
        resolver = ResolverService(client)

        resolved, metadata, _ = resolver.resolve_series(
            search_text="real gdp united states",
            geography="United States",
            indicator="real gdp",
        )

        self.assertEqual(resolved.series_id, "GDPC1")
        self.assertIn("Chained", metadata.units)

    def test_real_gdp_query_does_not_pick_growth_rate_series(self) -> None:
        client = _UnitsPreferenceFREDClient()
        resolver = ResolverService(client)

        resolved, _, _ = resolver.resolve_series(
            search_text="real gdp united states",
            geography="United States",
            indicator="real gdp",
        )

        self.assertNotEqual(resolved.series_id, "A191RL1Q225SBEA")

    def test_monthly_frequency_hint_boosts_monthly_candidate(self) -> None:
        client = _FrequencyPreferenceFREDClient()
        resolver = ResolverService(client)

        resolved, metadata, _ = resolver.resolve_series(
            search_text="monthly core pce price index",
            geography="United States",
            indicator="core pce",
        )

        self.assertEqual(metadata.frequency, "Monthly")


# ---------------------------------------------------------------------------
# Fixture suite: top-hit mistakes
# ---------------------------------------------------------------------------

class ResolverTopHitMistakeFixtures(unittest.TestCase):
    """FRED returns a market-instrument series first, but the reranker should
    pick the headline consumer price index instead."""

    def test_plain_inflation_reranks_away_from_breakeven_first_hit(self) -> None:
        client = _TopHitMistakeFREDClient()
        resolver = ResolverService(client)

        resolved, metadata, _ = resolver.resolve_series(
            search_text="inflation united states",
            geography="United States",
            indicator="inflation",
        )

        self.assertEqual(resolved.series_id, "CPIAUCSL")
        self.assertIn("reranked FRED search candidates", resolved.resolution_reason)

    def test_breakeven_not_selected_for_plain_inflation_with_geography_context(self) -> None:
        client = _TopHitMistakeFREDClient()
        resolver = ResolverService(client)

        resolved, _, _ = resolver.resolve_series(
            search_text="inflation united states",
            geography="United States",
            indicator="inflation",
        )

        self.assertNotEqual(resolved.series_id, "T5YIE")
        self.assertEqual(resolved.series_id, "CPIAUCSL")

    def test_plain_inflation_profile_scorer_penalizes_breakeven(self) -> None:
        breakeven_score = ResolverService._score_plain_inflation_profile(
            SeriesSearchMatch(
                series_id="T5YIE",
                title="5-Year Breakeven Inflation Rate",
                units="Percent",
                frequency="Daily",
                source_url="https://fred.stlouisfed.org/series/T5YIE",
            )
        )

        self.assertLess(breakeven_score, 0.0)


if __name__ == "__main__":
    unittest.main()
