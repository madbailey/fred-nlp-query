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


class _UnemploymentClarificationFREDClient:
    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        return [
            SeriesSearchMatch(
                series_id="UNRATE",
                title="Unemployment Rate",
                units="Percent",
                frequency="M",
                seasonal_adjustment="Seasonally Adjusted",
                popularity=95,
                source_url="https://fred.stlouisfed.org/series/UNRATE",
            ),
            SeriesSearchMatch(
                series_id="UNRATENSA",
                title="Unemployment Rate",
                units="Percent",
                frequency="M",
                seasonal_adjustment="Not Seasonally Adjusted",
                popularity=79,
                source_url="https://fred.stlouisfed.org/series/UNRATENSA",
            ),
        ]


class _IncomeClarificationFREDClient:
    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        return [
            SeriesSearchMatch(
                series_id="PI",
                title="Personal Income",
                units="Billions of Dollars",
                frequency="M",
                popularity=90,
                source_url="https://fred.stlouisfed.org/series/PI",
            ),
            SeriesSearchMatch(
                series_id="A792RC0Q052SBEA",
                title="Real Personal Income Per Capita",
                units="Chained 2017 Dollars",
                frequency="Q",
                popularity=72,
                source_url="https://fred.stlouisfed.org/series/A792RC0Q052SBEA",
            ),
        ]


class _SingleSeriesClarificationFREDClient:
    def search_series(self, search_text: str, limit: int = 5) -> list[SeriesSearchMatch]:
        return [
            SeriesSearchMatch(
                series_id="HOUST",
                title="Housing Starts: Total: New Privately Owned Housing Units Started",
                units="Thousands of Units",
                frequency="M",
                seasonal_adjustment="Seasonally Adjusted Annual Rate",
                popularity=83,
                source_url="https://fred.stlouisfed.org/series/HOUST",
            )
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

    def test_build_candidates_prefers_not_seasonally_adjusted_variants_when_requested(self) -> None:
        resolver = ClarificationResolver(_UnemploymentClarificationFREDClient())
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            clarification_needed=True,
            clarification_target_index=0,
            clarification_question=(
                "Which unemployment series should I use: seasonally adjusted unemployment rate "
                "or not seasonally adjusted unemployment rate?"
            ),
            search_text="unemployment rate",
        )

        candidates = resolver.build_candidates(intent)

        self.assertEqual(
            [candidate.series_id for candidate in candidates[:2]],
            ["UNRATENSA", "UNRATE"],
        )

    def test_build_candidates_prefers_per_capita_variants_when_requested(self) -> None:
        resolver = ClarificationResolver(_IncomeClarificationFREDClient())
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            clarification_needed=True,
            clarification_target_index=0,
            clarification_question=(
                "Which income series should I use: per capita personal income "
                "or aggregate personal income?"
            ),
            search_text="personal income",
        )

        candidates = resolver.build_candidates(intent)

        self.assertEqual(
            [candidate.series_id for candidate in candidates[:2]],
            ["A792RC0Q052SBEA", "PI"],
        )
        self.assertEqual(candidates[0].selection_label, "Real Per Capita Series")

    def test_annotate_candidates_populates_clarification_option_and_badges(self) -> None:
        resolver = ClarificationResolver(_CrowdedInflationClarificationFREDClient())
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            clarification_needed=True,
            clarification_target_index=0,
            clarification_question="Do you mean CPI or PCE inflation?",
            search_text="inflation",
        )

        annotated = resolver.annotate_candidates(
            [
                SeriesSearchMatch(
                    series_id="CPIAUCSL",
                    title="Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
                    units="Index 1982-1984=100",
                    frequency="M",
                    seasonal_adjustment="Seasonally Adjusted",
                    source_url="https://fred.stlouisfed.org/series/CPIAUCSL",
                )
            ],
            intent=intent,
        )

        option = annotated[0].clarification_option
        self.assertIsNotNone(option)
        self.assertEqual(option.label, "Headline CPI")
        self.assertEqual(option.title, annotated[0].title)
        self.assertIn("Pick this if you want CPI", option.hint or "")
        self.assertEqual(
            [(badge.kind, badge.label) for badge in option.badges],
            [
                ("frequency", "Monthly"),
                ("units", "Index level"),
                ("metadata", "Seasonally Adjusted"),
            ],
        )

    def test_build_candidates_handles_empty_clarification_question(self) -> None:
        resolver = ClarificationResolver(_SingleSeriesClarificationFREDClient())
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            clarification_needed=True,
            clarification_target_index=0,
            clarification_question=None,
            search_text="housing starts",
        )

        candidates = resolver.build_candidates(intent)

        self.assertEqual([candidate.series_id for candidate in candidates], ["HOUST"])

    def test_build_candidates_returns_empty_when_search_text_is_missing(self) -> None:
        resolver = ClarificationResolver(_SingleSeriesClarificationFREDClient())
        intent = QueryIntent(
            task_type=TaskType.SINGLE_SERIES_LOOKUP,
            clarification_needed=True,
            clarification_target_index=0,
            clarification_question="Which housing series should I use?",
        )

        self.assertEqual(resolver.build_candidates(intent), [])


if __name__ == "__main__":
    unittest.main()
