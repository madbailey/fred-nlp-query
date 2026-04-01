from __future__ import annotations

from dataclasses import dataclass, field

from fred_query.schemas.analysis import ObservationPoint


@dataclass
class SingleSeriesTransformResult:
    observations: list[ObservationPoint] | None
    basis: str | None
    units: str
    applied_window: int | None = None
    compare_on_transformed_series: bool = False
    warnings: list[str] = field(default_factory=list)
