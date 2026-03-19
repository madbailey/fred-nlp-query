from __future__ import annotations

from datetime import date

from fred_query.schemas.intent import ComparisonMode, Geography, GeographyType, QueryIntent, TaskType, TransformType


class IntentService:
    """Deterministic intent construction for the first workflow."""

    def build_state_gdp_comparison_intent(
        self,
        *,
        state1: str,
        state2: str,
        start_date: date,
        end_date: date | None,
        normalize: bool,
    ) -> QueryIntent:
        return QueryIntent(
            task_type=TaskType.STATE_GDP_COMPARISON,
            indicators=["real_gdp"],
            geographies=[
                Geography(name=state1, geography_type=GeographyType.STATE),
                Geography(name=state2, geography_type=GeographyType.STATE),
            ],
            comparison_mode=ComparisonMode.STATE_VS_STATE,
            start_date=start_date,
            end_date=end_date,
            frequency="annual",
            transform=TransformType.NORMALIZED_INDEX if normalize else TransformType.LEVEL,
            normalization=normalize,
            units_preference="Millions of Chained 2017 Dollars",
            needs_latest_value=True,
            needs_chart=True,
            needs_revision_analysis=False,
            clarification_needed=False,
        )
