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


if __name__ == "__main__":
    unittest.main()
