from __future__ import annotations

from datetime import date, timedelta

from fred_query.schemas.analysis import AnalysisResult, DerivedMetric, QueryIntent, QueryResponse, SeriesAnalysis
from fred_query.schemas.resolved_series import ResolvedSeries, SeriesMetadata
from fred_query.services.answer_service import AnswerService
from fred_query.services.chart_service import ChartService
from fred_query.services.fred_client import FREDClient
from fred_query.services.transform_service import TransformService


class RelationshipAnalysisService:
    """Deterministic pairwise analysis for non-state FRED relationship questions."""

    def __init__(
        self,
        fred_client: FREDClient,
        *,
        transform_service: TransformService | None = None,
        chart_service: ChartService | None = None,
        answer_service: AnswerService | None = None,
    ) -> None:
        self.fred_client = fred_client
        self.transform_service = transform_service or TransformService()
        self.chart_service = chart_service or ChartService()
        self.answer_service = answer_service or AnswerService()

    @staticmethod
    def _default_start_date() -> date:
        return date.today() - timedelta(days=365 * 10)

    @staticmethod
    def _indicator_for_index(intent: QueryIntent, index: int, fallback: str) -> str:
        if index < len(intent.indicators) and intent.indicators[index]:
            return intent.indicators[index]
        return fallback

    @staticmethod
    def _search_text_for_index(intent: QueryIntent, index: int) -> str | None:
        if index < len(intent.search_texts) and intent.search_texts[index]:
            return intent.search_texts[index]
        if len(intent.search_texts) == 1:
            return intent.search_texts[0]
        if index < len(intent.indicators) and intent.indicators[index]:
            return intent.indicators[index]
        return None

    @staticmethod
    def _series_id_for_index(intent: QueryIntent, index: int) -> str | None:
        if index < len(intent.series_ids) and intent.series_ids[index]:
            return intent.series_ids[index]
        return None

    @staticmethod
    def _lag_description(first_name: str, second_name: str, lag: int, lag_unit: str) -> str:
        if lag == 0:
            return "The strongest absolute correlation in the tested lag window occurs in the same period."
        if lag > 0:
            return f"Positive values mean {first_name} tends to lead {second_name} by {lag} {lag_unit}."
        return f"Negative values mean {second_name} tends to lead {first_name} by {abs(lag)} {lag_unit}."

    def _resolve_series(self, intent: QueryIntent, index: int) -> tuple[ResolvedSeries, SeriesMetadata]:
        explicit_series_id = self._series_id_for_index(intent, index)
        if explicit_series_id:
            metadata = self.fred_client.get_series_metadata(explicit_series_id)
            return (
                ResolvedSeries(
                    series_id=metadata.series_id,
                    title=metadata.title,
                    geography="Unspecified",
                    indicator=self._indicator_for_index(intent, index, metadata.title),
                    units=metadata.units,
                    frequency=metadata.frequency,
                    seasonal_adjustment=metadata.seasonal_adjustment,
                    score=1.0,
                    resolution_reason=f"Used explicit series ID {metadata.series_id}.",
                    source_url=metadata.source_url,
                ),
                metadata,
            )

        search_text = self._search_text_for_index(intent, index)
        if not search_text:
            raise ValueError("I need two resolvable series targets before I can run relationship analysis.")

        matches = self.fred_client.search_series(search_text, limit=5)
        if not matches:
            raise ValueError(f"No FRED series matched search text '{search_text}'.")

        search_match = matches[0]
        metadata = self.fred_client.get_series_metadata(search_match.series_id)
        return (
            ResolvedSeries(
                series_id=metadata.series_id,
                title=metadata.title,
                geography="Unspecified",
                indicator=self._indicator_for_index(intent, index, search_text),
                units=metadata.units,
                frequency=metadata.frequency,
                seasonal_adjustment=metadata.seasonal_adjustment,
                score=0.8,
                resolution_reason=f"Resolved the query via FRED search. Top match was {metadata.series_id}.",
                source_url=metadata.source_url,
            ),
            metadata,
        )

    def analyze(self, intent: QueryIntent) -> QueryResponse:
        resolved_series: list[ResolvedSeries] = []
        metadata_items: list[SeriesMetadata] = []
        for index in range(2):
            resolved, metadata = self._resolve_series(intent, index)
            resolved_series.append(resolved)
            metadata_items.append(metadata)

        frequency_code, frequency_label, periods_per_year, lag_unit = (
            self.transform_service.choose_relationship_frequency(
                [metadata.frequency for metadata in metadata_items]
            )
        )

        start_date = intent.start_date or self._default_start_date()
        end_date = intent.end_date
        raw_observations: list[list] = []
        transformed_observations: list[list] = []
        bases: list[str] = []
        analysis_units: list[str] = []

        for metadata in metadata_items:
            observations = self.fred_client.get_series_observations(
                metadata.series_id,
                start_date=start_date,
                end_date=end_date,
                frequency=frequency_code,
                aggregation_method="avg",
            )
            if not observations:
                raise ValueError(f"No observations returned for {metadata.series_id}.")

            transformed, basis, units = self.transform_service.build_relationship_basis(
                observations,
                title=metadata.title,
                units=metadata.units,
                periods_per_year=periods_per_year,
            )
            if not transformed:
                raise ValueError(
                    f"I could not derive a stable comparison basis for {metadata.series_id} over the requested date range."
                )

            raw_observations.append(observations)
            transformed_observations.append(transformed)
            bases.append(basis)
            analysis_units.append(units)

        aligned_first, aligned_second = self.transform_service.align_on_dates(
            transformed_observations[0],
            transformed_observations[1],
        )
        if len(aligned_first) < 8:
            raise ValueError(
                "The two series do not have enough overlapping observations after alignment to estimate a relationship safely."
            )

        same_period_correlation = self.transform_service.calculate_correlation(aligned_first, aligned_second)
        regression_slope = self.transform_service.calculate_regression_slope(aligned_first, aligned_second)
        best_lag, best_lag_correlation, best_lag_samples = self.transform_service.calculate_best_lag_correlation(
            aligned_first,
            aligned_second,
            max_lag=self.transform_service.relationship_max_lag(periods_per_year),
        )

        chart_series = [aligned_first, aligned_second]
        chart_units = analysis_units[0]
        warnings: list[str] = []
        basis_summary = (
            bases[0]
            if bases[0] == bases[1]
            else f"{resolved_series[0].series_id}: {bases[0]}; {resolved_series[1].series_id}: {bases[1]}"
        )
        chart_basis = basis_summary
        if analysis_units[0] != analysis_units[1]:
            chart_series = [
                self.transform_service.standardize(aligned_first),
                self.transform_service.standardize(aligned_second),
            ]
            chart_units = "Standard deviations"
            chart_basis = "Standardized relationship basis"
            warnings.append(
                "Chart values were standardized because the analysis basis produced different units across the two series."
            )

        latest_dates = [series[-1].date for series in raw_observations]
        latest_values = [series[-1].value for series in raw_observations]
        series_results = [
            SeriesAnalysis(
                series=resolved_series[index],
                observations=raw_observations[index],
                transformed_observations=chart_series[index],
                analysis_basis=bases[index],
                analysis_units=analysis_units[index],
                latest_value=latest_values[index],
                latest_observation_date=latest_dates[index],
            )
            for index in range(2)
        ]

        derived_metrics = [
            DerivedMetric(
                name="analysis_basis",
                value=basis_summary,
                description="Transformation used to make the pairwise comparison more stable and interpretable.",
            ),
            DerivedMetric(
                name="common_frequency",
                value=frequency_label,
                description="Frequency used to align the two series before estimating the relationship.",
            ),
            DerivedMetric(
                name="overlap_observations",
                value=len(aligned_first),
                unit="observations",
                description="Number of aligned observations used in the same-period relationship estimate.",
            ),
        ]

        if same_period_correlation is not None:
            derived_metrics.append(
                DerivedMetric(
                    name="same_period_correlation",
                    value=round(same_period_correlation, 4),
                    description="Pearson correlation on the aligned analysis basis in the same period.",
                )
            )

        if regression_slope is not None:
            derived_metrics.append(
                DerivedMetric(
                    name="regression_slope",
                    value=round(regression_slope, 4),
                    description=(
                        f"Simple linear slope of {resolved_series[1].series_id} on {resolved_series[0].series_id} "
                        "using the aligned analysis basis."
                    ),
                )
            )

        if best_lag is not None and best_lag_correlation is not None:
            derived_metrics.extend(
                [
                    DerivedMetric(
                        name="strongest_lag_periods",
                        value=best_lag,
                        unit=lag_unit,
                        description=self._lag_description(
                            resolved_series[0].series_id,
                            resolved_series[1].series_id,
                            best_lag,
                            lag_unit,
                        ),
                    ),
                    DerivedMetric(
                        name="strongest_lag_correlation",
                        value=round(best_lag_correlation, 4),
                        description=(
                            f"Absolute strongest correlation in the tested lead-lag window using {best_lag_samples} "
                            "overlapping observations."
                        ),
                    ),
                ]
            )

        analysis = AnalysisResult(
            series_results=series_results,
            derived_metrics=derived_metrics,
            warnings=warnings,
            latest_observation_date=max(latest_dates),
            coverage_start=aligned_first[0].date,
            coverage_end=aligned_first[-1].date,
        )
        chart = self.chart_service.build_relationship_chart(
            series_results=series_results,
            frequency_label=frequency_label,
            chart_basis=chart_basis,
            chart_units=chart_units,
            start_date=aligned_first[0].date,
            end_date=aligned_first[-1].date,
        )
        answer_text = self.answer_service.write_relationship_analysis(analysis)
        return QueryResponse(intent=intent, analysis=analysis, chart=chart, answer_text=answer_text)
