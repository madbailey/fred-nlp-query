from __future__ import annotations

import unittest

from fred_query.schemas.intent import ComparisonMode, QueryIntent, TaskType
from fred_query.schemas.resolved_series import SeriesSearchMatch
from fred_query.services.clarification_resolver import ClarificationResolver


class _CrowdedInflationClarificationFREDClient:
    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        lowered = search_text.lower()
        if "cpi" in lowered:
            return [
                SeriesSearchMatch(
                    series_id="CPIAUCSL",
                    title="Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
                    units="Index 1982-1984=100",
                    frequency="M",
                    popularity=95,
                    source_url="https://fred.stlouisfed.org/series/CPIAUCSL",
                )
            ]
        if "pce" in lowered:
            return [
                SeriesSearchMatch(
                    series_id="PCETRIM12M159SFRBDAL",
                    title="Trimmed Mean PCE Inflation Rate",
                    units="% Chg. from Yr. Ago",
                    frequency="M",
                    popularity=82,
                    source_url="https://fred.stlouisfed.org/series/PCETRIM12M159SFRBDAL",
                ),
                SeriesSearchMatch(
                    series_id="PCEPI",
                    title="Personal Consumption Expenditures: Chain-type Price Index",
                    units="Index 2017=100",
                    frequency="M",
                    popularity=88,
                    source_url="https://fred.stlouisfed.org/series/PCEPI",
                ),
            ]
        return [
            SeriesSearchMatch(
                series_id="PCETRIM12M159SFRBDAL",
                title="Trimmed Mean PCE Inflation Rate",
                units="% Chg. from Yr. Ago",
                frequency="M",
                popularity=82,
                source_url="https://fred.stlouisfed.org/series/PCETRIM12M159SFRBDAL",
            ),
            SeriesSearchMatch(
                series_id="PCETRIM1M158SFRBDAL",
                title="Trimmed Mean PCE Inflation Rate",
                units="% Chg. at Annual Rate",
                frequency="M",
                popularity=80,
                source_url="https://fred.stlouisfed.org/series/PCETRIM1M158SFRBDAL",
            ),
            SeriesSearchMatch(
                series_id="PCEPI",
                title="Personal Consumption Expenditures: Chain-type Price Index",
                units="Index 2017=100",
                frequency="M",
                popularity=88,
                source_url="https://fred.stlouisfed.org/series/PCEPI",
            ),
            SeriesSearchMatch(
                series_id="CPIAUCSL",
                title="Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
                units="Index 1982-1984=100",
                frequency="M",
                popularity=95,
                source_url="https://fred.stlouisfed.org/series/CPIAUCSL",
            ),
        ]


class _GDPClarificationFREDClient:
    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        lowered = search_text.lower()
        if "real gdp" in lowered:
            return [
                SeriesSearchMatch(
                    series_id="GDPC1",
                    title="Real Gross Domestic Product",
                    units="Billions of Chained 2017 Dollars",
                    frequency="Q",
                    seasonal_adjustment="SAAR",
                    popularity=91,
                    source_url="https://fred.stlouisfed.org/series/GDPC1",
                )
            ]
        if "nominal gdp" in lowered:
            return [
                SeriesSearchMatch(
                    series_id="GDP",
                    title="Gross Domestic Product",
                    units="Billions of Current Dollars",
                    frequency="Q",
                    seasonal_adjustment="SAAR",
                    popularity=94,
                    source_url="https://fred.stlouisfed.org/series/GDP",
                )
            ]
        if "gdp growth" in lowered:
            return [
                SeriesSearchMatch(
                    series_id="A191RL1Q225SBEA",
                    title="Real Gross Domestic Product",
                    units="Percent Change from Preceding Period",
                    frequency="Q",
                    seasonal_adjustment="SAAR",
                    popularity=78,
                    source_url="https://fred.stlouisfed.org/series/A191RL1Q225SBEA",
                )
            ]
        return [
            SeriesSearchMatch(
                series_id="A191RL1Q225SBEA",
                title="Real Gross Domestic Product",
                units="Percent Change from Preceding Period",
                frequency="Q",
                seasonal_adjustment="SAAR",
                popularity=78,
                source_url="https://fred.stlouisfed.org/series/A191RL1Q225SBEA",
            ),
            SeriesSearchMatch(
                series_id="GDP",
                title="Gross Domestic Product",
                units="Billions of Current Dollars",
                frequency="Q",
                seasonal_adjustment="SAAR",
                popularity=94,
                source_url="https://fred.stlouisfed.org/series/GDP",
            ),
            SeriesSearchMatch(
                series_id="GDPC1",
                title="Real Gross Domestic Product",
                units="Billions of Chained 2017 Dollars",
                frequency="Q",
                seasonal_adjustment="SAAR",
                popularity=91,
                source_url="https://fred.stlouisfed.org/series/GDPC1",
            ),
        ]


class ClarificationResolverTest(unittest.TestCase):
    def test_build_candidates_prioritizes_examples_and_dedupes_variants(self) -> None:
        resolver = ClarificationResolver(_CrowdedInflationClarificationFREDClient())
        intent = QueryIntent(
            task_type=TaskType.RELATIONSHIP_ANALYSIS,
            comparison_mode=ComparisonMode.RELATIONSHIP,
            clarification_needed=True,
            clarification_target_index=1,
            clarification_question=(
                "Which inflation series should I use: CPI inflation (CPI-U), "
                "PCE inflation, or another inflation measure?"
            ),
            search_texts=["brent crude oil price", "inflation united states"],
        )

        candidates = resolver.build_candidates(intent)

        self.assertEqual(
            [candidate.series_id for candidate in candidates],
            ["CPIAUCSL", "PCEPI", "PCETRIM12M159SFRBDAL"],
        )
        self.assertEqual(
            [candidate.selection_label for candidate in candidates],
            ["Headline CPI", "Headline PCE", "Trimmed Mean PCE"],
        )
        self.assertEqual(len({candidate.title for candidate in candidates}), len(candidates))

    def test_build_candidates_adds_generic_labels_and_hints_for_real_nominal_and_growth_variants(self) -> None:
        resolver = ClarificationResolver(_GDPClarificationFREDClient())
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            clarification_needed=True,
            clarification_target_index=0,
            clarification_question="Which GDP series should I use: real GDP, nominal GDP, or GDP growth?",
            search_text="gdp united states",
        )

        candidates = resolver.build_candidates(intent)

        self.assertEqual(
            [candidate.series_id for candidate in candidates],
            ["GDPC1", "GDP", "A191RL1Q225SBEA"],
        )
        self.assertEqual(
            [candidate.selection_label for candidate in candidates],
            ["Real Series", "Nominal Series", "Real Growth Rate"],
        )
        self.assertIn("inflation-adjusted version", candidates[0].selection_hint or "")
        self.assertIn("nominal/current-dollar version", candidates[1].selection_hint or "")
        self.assertIn("growth-rate version", candidates[2].selection_hint or "")


if __name__ == "__main__":
    unittest.main()
