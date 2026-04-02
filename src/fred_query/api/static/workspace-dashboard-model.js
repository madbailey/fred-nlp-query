import {
    formatDate,
    formatFrequencyLabel,
    formatPercent,
    formatValue,
    humanize,
    truncateText,
} from "./workspace-utils.js";

const TASK_TYPES = {
    SINGLE_SERIES: "single_series_lookup",
    CROSS_SECTION: "cross_section",
    STATE_COMPARISON: "state_gdp_comparison",
    MULTI_SERIES: "multi_series_comparison",
    RELATIONSHIP: "relationship_analysis",
};

const CROSS_SECTION_SCOPE_LABELS = {
    single_series: "Single series",
    provided_geographies: "Selected geographies",
    states: "All states",
};

function getMetricMap(analysis) {
    return new Map((analysis?.derived_metrics || []).map((metric) => [metric.name, metric]));
}

function getMetric(metrics, name) {
    return metrics.get(name) || null;
}

function asNumber(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return null;
    }
    return Number(value);
}

function formatSignedValue(value, unit) {
    const numeric = asNumber(value);
    if (numeric === null) {
        return "N/A";
    }

    const sign = numeric > 0 ? "+" : numeric < 0 ? "-" : "";
    const absolute = Math.abs(numeric);
    const normalizedUnit = (unit || "").trim().toLowerCase();

    if (normalizedUnit.includes("percentage point")) {
        return `${sign}${formatValue(absolute)} pp`;
    }
    if (normalizedUnit === "%" || normalizedUnit.includes("percent")) {
        return `${sign}${formatValue(absolute)}%`;
    }
    return `${sign}${formatValue(absolute)}`;
}

function compactUnit(units) {
    const normalized = (units || "").trim().toLowerCase();
    if (!normalized) {
        return "";
    }
    if (normalized === "%" || normalized.includes("percent")) {
        return "%";
    }
    if (normalized === "bps" || normalized.includes("basis point")) {
        return "bps";
    }
    return "";
}

function formatValueWithUnit(value, units) {
    const formatted = formatValue(value);
    if (formatted === "N/A") {
        return formatted;
    }

    const shorthandUnit = compactUnit(units);
    if (shorthandUnit === "%") {
        return `${formatted}%`;
    }
    if (shorthandUnit === "bps") {
        return `${formatted} bps`;
    }
    return formatted;
}

function formatRatio(value) {
    const numeric = asNumber(value);
    if (numeric === null) {
        return "N/A";
    }
    return `${formatValue(numeric)}x`;
}

function formatCorrelation(value) {
    const numeric = asNumber(value);
    if (numeric === null) {
        return "N/A";
    }
    return formatValue(numeric);
}

function formatLag(value, unit) {
    const numeric = asNumber(value);
    if (numeric === null) {
        return "N/A";
    }
    if (numeric === 0) {
        return "Same period";
    }

    const normalizedUnit = (unit || "periods").trim();
    const rounded = Math.round(Math.abs(numeric));
    const singularUnit = normalizedUnit.endsWith("s") ? normalizedUnit.slice(0, -1) : normalizedUnit;
    const label = rounded === 1 ? singularUnit : normalizedUnit;
    return `${rounded} ${label}`;
}

function toOrdinal(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "N/A";
    }

    const rounded = Math.max(1, Math.min(100, Math.round(Number(value))));
    const suffix = (rounded % 100 >= 11 && rounded % 100 <= 13)
        ? "th"
        : ({ 1: "st", 2: "nd", 3: "rd" }[rounded % 10] || "th");
    return `${rounded}${suffix}`;
}

function extractDateFromDescription(description) {
    const match = (description || "").match(/(\d{4}-\d{2}-\d{2})/);
    return match?.[1] || null;
}

function formatCoverage(analysis) {
    if (!analysis?.coverage_start && !analysis?.coverage_end) {
        return "Latest available";
    }
    if (analysis?.coverage_start && analysis?.coverage_end) {
        return `${formatDate(analysis.coverage_start)} to ${formatDate(analysis.coverage_end)}`;
    }
    return formatDate(analysis?.coverage_start || analysis?.coverage_end);
}

function formatYearRange(analysis) {
    if (!analysis?.coverage_start && !analysis?.coverage_end) {
        return "";
    }

    const startYear = analysis?.coverage_start
        ? new Date(`${analysis.coverage_start}T00:00:00`).getFullYear()
        : null;
    const endYear = analysis?.coverage_end
        ? new Date(`${analysis.coverage_end}T00:00:00`).getFullYear()
        : null;

    if (startYear && endYear) {
        return startYear === endYear ? String(startYear) : `${startYear}-${endYear}`;
    }
    return String(startYear || endYear || "");
}

function compactBasis(basis) {
    const text = (basis || "").trim();
    const normalized = text.toLowerCase();
    if (!normalized) {
        return "";
    }
    if (normalized.includes("year over year")) {
        return "YoY change";
    }
    if (normalized.includes("period over period")) {
        return "PoP change";
    }
    if (normalized.includes("normalized index")) {
        return "Indexed level";
    }
    if (normalized.includes("rolling average")) {
        return "Rolling avg";
    }
    if (normalized.includes("rolling volatility")) {
        return "Rolling vol";
    }
    if (normalized.includes("rolling stddev")) {
        return "Rolling std dev";
    }
    if (normalized === "level" || normalized === "reported levels") {
        return "Reported level";
    }
    return truncateText(text, 36);
}

function formatDisplaySelectionBasis(value) {
    const normalized = (value || "").trim().toLowerCase();
    if (!normalized) {
        return "";
    }
    if (normalized === "comparison_context") {
        return "Context slice";
    }
    if (normalized === "explicit_request") {
        return "Requested limit";
    }
    if (normalized === "full_result_set") {
        return "Full result";
    }
    if (normalized === "default_limit") {
        return "Default slice";
    }
    return humanize(normalized);
}

function formatCrossSectionScope(scope) {
    return CROSS_SECTION_SCOPE_LABELS[scope] || humanize(scope) || "";
}

function formatSeriesLabel(result) {
    const geography = (result?.series?.geography || "").trim();
    if (geography && geography.toLowerCase() !== "unspecified") {
        return geography;
    }
    return result?.series?.title || result?.series?.series_id || "Series";
}

function formatSeriesSubtitle(result) {
    const title = (result?.series?.title || "").trim();
    const label = formatSeriesLabel(result);
    if (!title || title === label) {
        return result?.series?.series_id || "";
    }
    return truncateText(title, 72);
}

function describeCorrelation(value) {
    const numeric = asNumber(value);
    if (numeric === null) {
        return "";
    }

    const absolute = Math.abs(numeric);
    if (absolute >= 0.8) {
        return numeric >= 0 ? "very strong positive" : "very strong inverse";
    }
    if (absolute >= 0.6) {
        return numeric >= 0 ? "strong positive" : "strong inverse";
    }
    if (absolute >= 0.35) {
        return numeric >= 0 ? "moderate positive" : "moderate inverse";
    }
    if (absolute >= 0.15) {
        return numeric >= 0 ? "modest positive" : "modest inverse";
    }
    return numeric >= 0 ? "weak positive" : "weak inverse";
}

function buildSeriesDetails(results) {
    return (results || []).flatMap((result) => {
        const label = formatSeriesLabel(result);
        return [
            { label: `${label} series`, value: result.series.series_id },
            result.series.source_url
                ? { label: `${label} source`, value: "Open in FRED", href: result.series.source_url }
                : null,
        ].filter(Boolean);
    });
}

function buildSeriesCard(result, { emphasizeGrowth = false } = {}) {
    const latestUnits = result.analysis_units || result.series.units;
    return {
        label: truncateText(formatSeriesLabel(result), 28),
        title: formatSeriesSubtitle(result),
        value: formatValueWithUnit(result.latest_value, latestUnits),
        note: result.latest_observation_date ? `Latest ${formatDate(result.latest_observation_date)}` : "Latest available",
        meta: [
            emphasizeGrowth && result.total_growth_pct !== null && result.total_growth_pct !== undefined
                ? `Growth ${formatPercent(result.total_growth_pct)}`
                : null,
            result.analysis_basis ? compactBasis(result.analysis_basis) : null,
            result.series.series_id || null,
        ].filter(Boolean),
    };
}

function buildInsight(result, analysis, metrics) {
    const latestValue = result.latest_value;
    const latestUnits = result.analysis_units || result.series.units;
    const averageMetric = getMetric(metrics, "historical_average");
    const percentileMetric = getMetric(metrics, "historical_percentile_rank");
    const peakMetric = getMetric(metrics, "historical_peak");
    const troughMetric = getMetric(metrics, "historical_trough");

    const clauses = [];
    if (averageMetric && latestValue !== null && latestValue !== undefined && !Number.isNaN(Number(latestValue))) {
        const relation = Number(latestValue) > Number(averageMetric.value)
            ? "above"
            : Number(latestValue) < Number(averageMetric.value)
                ? "below"
                : "in line with";
        clauses.push(
            `Latest reading is ${relation} the long-run average of ${formatValueWithUnit(averageMetric.value, averageMetric.unit || latestUnits)}.`,
        );
    }
    if (percentileMetric) {
        clauses.push(`It sits in the ${toOrdinal(percentileMetric.value)} percentile of the historical window.`);
    }

    const support = [];
    if (peakMetric) {
        const peakDate = extractDateFromDescription(peakMetric.description);
        support.push(
            peakDate
                ? `Peak was ${formatValueWithUnit(peakMetric.value, peakMetric.unit || latestUnits)} on ${formatDate(peakDate)}.`
                : `Peak was ${formatValueWithUnit(peakMetric.value, peakMetric.unit || latestUnits)}.`,
        );
    }
    if (troughMetric) {
        const troughDate = extractDateFromDescription(troughMetric.description);
        support.push(
            troughDate
                ? `Trough was ${formatValueWithUnit(troughMetric.value, troughMetric.unit || latestUnits)} on ${formatDate(troughDate)}.`
                : `Trough was ${formatValueWithUnit(troughMetric.value, troughMetric.unit || latestUnits)}.`,
        );
    }
    if (result.total_growth_pct !== null && result.total_growth_pct !== undefined) {
        const startYear = analysis?.coverage_start ? new Date(`${analysis.coverage_start}T00:00:00`).getFullYear() : null;
        support.push(startYear ? `${formatPercent(result.total_growth_pct)} since ${startYear}.` : `${formatPercent(result.total_growth_pct)} over the selected window.`);
    }
    if (result.analysis_basis) {
        support.push(`Chart shows ${result.analysis_basis.toLowerCase()}.`);
    } else {
        support.push("Chart shows reported levels.");
    }

    return {
        lead: clauses[0] || `Latest reading is ${formatValueWithUnit(latestValue, latestUnits)}.`,
        support: clauses.slice(1).concat(support).slice(0, 4),
    };
}

function buildHeroStats(result, metrics) {
    const latestUnits = result.analysis_units || result.series.units;
    const averageMetric = getMetric(metrics, "historical_average");
    const percentileMetric = getMetric(metrics, "historical_percentile_rank");

    return [
        result.total_growth_pct !== null && result.total_growth_pct !== undefined
            ? {
                label: "Since start",
                value: formatPercent(result.total_growth_pct),
                note: "Window change",
            }
            : null,
        averageMetric
            ? {
                label: "Long-run avg",
                value: formatValueWithUnit(averageMetric.value, averageMetric.unit || latestUnits),
                note: "Historical context",
            }
            : null,
        percentileMetric
            ? {
                label: "Percentile",
                value: toOrdinal(percentileMetric.value),
                note: "Historical window",
            }
            : null,
        result.compound_annual_growth_rate_pct !== null && result.compound_annual_growth_rate_pct !== undefined
            ? {
                label: "CAGR",
                value: formatPercent(result.compound_annual_growth_rate_pct),
                note: "Annualized",
            }
            : null,
    ].filter(Boolean);
}

function buildDetails(result, analysis, metrics) {
    const latestUnits = result.analysis_units || result.series.units;
    const basisMetric = getMetric(metrics, "analysis_basis");
    return [
        { label: "Series", value: result.series.series_id },
        { label: "Frequency", value: formatFrequencyLabel(result.series.frequency) || result.series.frequency },
        result.series.seasonal_adjustment ? { label: "Adjustment", value: result.series.seasonal_adjustment } : null,
        latestUnits ? { label: "Units", value: truncateText(latestUnits, 28) } : null,
        {
            label: "Coverage",
            value: analysis?.coverage_start && analysis?.coverage_end
                ? `${formatDate(analysis.coverage_start)} to ${formatDate(analysis.coverage_end)}`
                : "Latest available",
        },
        {
            label: "Basis",
            value: basisMetric?.value
                ? humanize(basisMetric.value)
                : (result.analysis_basis ? humanize(result.analysis_basis) : "Reported levels"),
        },
        result.series.source_url
            ? { label: "Source", value: "Open in FRED", href: result.series.source_url }
            : null,
    ].filter(Boolean);
}

function buildActions(response) {
    return (response.follow_up_suggestions || [])
        .map((item) => {
            const query = typeof item === "string" ? item : item?.query;
            const label = typeof item === "string" ? item : (item?.label || item?.query);
            if (!query) {
                return null;
            }
            return {
                query,
                label: truncateText(label || query, 72),
                title: label || query,
            };
        })
        .filter(Boolean)
        .slice(0, 3);
}

function buildSingleSeriesDashboardModel(response) {
    const analysis = response?.result?.analysis;
    const result = analysis?.series_results?.[0];
    if (!analysis || !result) {
        return null;
    }

    const metrics = getMetricMap(analysis);
    const latestUnits = result.analysis_units || result.series.units;

    return {
        mode: "single_series",
        title: result.series.title,
        badges: [
            result.series.series_id,
            formatFrequencyLabel(result.series.frequency) || result.series.frequency,
            result.series.seasonal_adjustment,
        ].filter(Boolean),
        latest: {
            label: result.analysis_basis ? `Latest ${result.analysis_basis.toLowerCase()}` : "Latest reading",
            value: formatValueWithUnit(result.latest_value, latestUnits),
            note: result.latest_observation_date ? formatDate(result.latest_observation_date) : "Latest available",
        },
        heroStats: buildHeroStats(result, metrics),
        insight: buildInsight(result, analysis, metrics),
        details: buildDetails(result, analysis, metrics),
        actions: buildActions(response),
        warnings: analysis.warnings || [],
    };
}

function buildStateComparisonInsight(response, analysis, metrics) {
    const [first, second] = analysis.series_results;
    const firstLabel = formatSeriesLabel(first);
    const secondLabel = formatSeriesLabel(second);
    const growthDifference = asNumber(getMetric(metrics, "growth_difference_pct")?.value);
    const sizeRatio = asNumber(getMetric(metrics, "latest_size_ratio")?.value);

    let lead = `This view compares ${firstLabel} and ${secondLabel} over the same period.`;
    if (growthDifference !== null) {
        if (growthDifference > 0) {
            lead = `${firstLabel} outpaced ${secondLabel} over the selected window.`;
        } else if (growthDifference < 0) {
            lead = `${secondLabel} outpaced ${firstLabel} over the selected window.`;
        } else {
            lead = `${firstLabel} and ${secondLabel} posted the same total growth over the selected window.`;
        }
    }

    const support = [];
    if (first.total_growth_pct !== null && second.total_growth_pct !== null) {
        support.push(
            `${firstLabel}: ${formatPercent(first.total_growth_pct)} total growth. ${secondLabel}: ${formatPercent(second.total_growth_pct)}.`,
        );
    }
    if (sizeRatio !== null && sizeRatio > 0) {
        support.push(
            sizeRatio >= 1
                ? `Latest level leaves ${firstLabel} at ${formatRatio(sizeRatio)} of ${secondLabel}.`
                : `Latest level leaves ${secondLabel} at ${formatRatio(1 / sizeRatio)} of ${firstLabel}.`,
        );
    }
    support.push(
        response.intent?.normalization
            ? "Chart is indexed to the first observation so relative growth is easier to compare."
            : "Chart shows reported GDP levels rather than an indexed growth baseline.",
    );
    support.push(`Window covers ${formatCoverage(analysis)}.`);

    return { lead, support: support.slice(0, 4) };
}

function buildStateComparisonDashboardModel(response) {
    const analysis = response?.result?.analysis;
    const [first, second] = analysis?.series_results || [];
    if (!analysis || !first || !second) {
        return null;
    }

    const metrics = getMetricMap(analysis);
    const firstLabel = formatSeriesLabel(first);
    const secondLabel = formatSeriesLabel(second);
    const growthDifferenceMetric = getMetric(metrics, "growth_difference_pct");
    const growthDifference = asNumber(growthDifferenceMetric?.value);
    const sizeRatio = asNumber(getMetric(metrics, "latest_size_ratio")?.value);

    return {
        mode: "comparison",
        title: `${firstLabel} vs ${secondLabel}`,
        badges: [
            "State GDP",
            response.intent?.normalization ? "Indexed growth" : "Level view",
            formatYearRange(analysis),
        ].filter(Boolean),
        summary: {
            label: growthDifference !== null ? "Growth gap" : "Comparison snapshot",
            value: growthDifference !== null ? formatSignedValue(growthDifference, growthDifferenceMetric?.unit) : `${firstLabel} vs ${secondLabel}`,
            note: growthDifference > 0
                ? `${firstLabel} ahead in total growth`
                : growthDifference < 0
                    ? `${secondLabel} ahead in total growth`
                    : growthDifference === 0
                        ? "Even total growth over the window"
                        : "Matched period comparison",
        },
        heroStats: [
            first.total_growth_pct !== null && first.total_growth_pct !== undefined
                ? { label: truncateText(`${firstLabel} growth`, 22), value: formatPercent(first.total_growth_pct), note: "Total window" }
                : null,
            second.total_growth_pct !== null && second.total_growth_pct !== undefined
                ? { label: truncateText(`${secondLabel} growth`, 22), value: formatPercent(second.total_growth_pct), note: "Total window" }
                : null,
            sizeRatio !== null && sizeRatio > 0
                ? {
                    label: "Size ratio",
                    value: sizeRatio >= 1 ? formatRatio(sizeRatio) : formatRatio(1 / sizeRatio),
                    note: sizeRatio >= 1 ? `${firstLabel} vs ${secondLabel}` : `${secondLabel} vs ${firstLabel}`,
                }
                : null,
            analysis.coverage_end
                ? { label: "Latest", value: formatDate(analysis.coverage_end), note: "Observation end" }
                : null,
        ].filter(Boolean).slice(0, 4),
        pairCards: [
            buildSeriesCard(first, { emphasizeGrowth: true }),
            buildSeriesCard(second, { emphasizeGrowth: true }),
        ],
        insight: buildStateComparisonInsight(response, analysis, metrics),
        details: [
            { label: "Comparison basis", value: response.intent?.normalization ? "Normalized index (100 at start)" : "Reported GDP levels" },
            { label: "Coverage", value: formatCoverage(analysis) },
            ...buildSeriesDetails([first, second]),
        ],
        actions: buildActions(response),
        warnings: analysis.warnings || [],
    };
}

function buildPairInsight(response, analysis, summary) {
    const [first, second] = analysis.series_results;
    const firstLabel = formatSeriesLabel(first);
    const secondLabel = formatSeriesLabel(second);
    const samePeriodCorrelation = asNumber(summary?.same_period_correlation);
    const strongestLag = asNumber(summary?.strongest_lag_periods);
    const strongestLagCorrelation = asNumber(summary?.strongest_lag_correlation);
    const strongestLagUnit = summary?.strongest_lag_unit || "periods";
    const isRelationship = response.intent?.task_type === TASK_TYPES.RELATIONSHIP;
    const relationshipText = describeCorrelation(samePeriodCorrelation);

    let lead = `This view aligns ${firstLabel} and ${secondLabel} on a common basis for comparison.`;
    if (samePeriodCorrelation !== null) {
        lead = isRelationship
            ? `${firstLabel} and ${secondLabel} show ${relationshipText} co-movement on the aligned basis.`
            : `${firstLabel} and ${secondLabel} moved with ${relationshipText} co-movement over the selected window.`;
    }

    const support = [];
    if (summary?.analysis_basis) {
        support.push(`Analysis basis: ${summary.analysis_basis}.`);
    }
    if (summary?.common_frequency) {
        support.push(`Aligned at ${summary.common_frequency.toLowerCase()} frequency.`);
    }
    if (strongestLag !== null && strongestLagCorrelation !== null) {
        if (strongestLag > 0) {
            support.push(
                `${firstLabel} leads ${secondLabel} by ${formatLag(strongestLag, strongestLagUnit)} at the strongest tested correlation of ${formatCorrelation(strongestLagCorrelation)}.`,
            );
        } else if (strongestLag < 0) {
            support.push(
                `${secondLabel} leads ${firstLabel} by ${formatLag(strongestLag, strongestLagUnit)} at the strongest tested correlation of ${formatCorrelation(strongestLagCorrelation)}.`,
            );
        } else {
            support.push(
                `The strongest tested relationship is contemporaneous, with a correlation of ${formatCorrelation(strongestLagCorrelation)}.`,
            );
        }
    } else if (summary?.overlap_observations !== null && summary?.overlap_observations !== undefined) {
        support.push(`${formatValue(summary.overlap_observations)} overlapping observations used after alignment.`);
    }
    if (isRelationship) {
        support.push("This is an association estimate, not evidence of causation.");
    }

    return { lead, support: support.slice(0, 4) };
}

function buildPairAnalysisDashboardModel(response) {
    const analysis = response?.result?.analysis;
    const [first, second] = analysis?.series_results || [];
    const summary = analysis?.relationship_summary;
    if (!analysis || !first || !second || !summary) {
        return null;
    }

    const firstLabel = formatSeriesLabel(first);
    const secondLabel = formatSeriesLabel(second);
    const samePeriodCorrelation = asNumber(summary.same_period_correlation);
    const strongestLag = asNumber(summary.strongest_lag_periods);
    const strongestLagCorrelation = asNumber(summary.strongest_lag_correlation);
    const overlapObservations = asNumber(summary.overlap_observations);
    const isRelationship = response.intent?.task_type === TASK_TYPES.RELATIONSHIP;

    return {
        mode: "pair_analysis",
        variant: isRelationship ? "relationship" : "comparison",
        title: `${truncateText(firstLabel, 28)} vs ${truncateText(secondLabel, 28)}`,
        badges: [
            isRelationship ? "Relationship estimate" : "Pair comparison",
            summary.common_frequency || "",
            compactBasis(summary.analysis_basis),
        ].filter(Boolean),
        summary: {
            label: isRelationship ? "Same-period correlation" : "Aligned basis",
            value: isRelationship ? formatCorrelation(samePeriodCorrelation) : compactBasis(summary.analysis_basis) || "Aligned",
            note: isRelationship
                ? `${describeCorrelation(samePeriodCorrelation)} link`
                : `${summary.common_frequency || "Aligned"} comparison`,
        },
        heroStats: [
            samePeriodCorrelation !== null
                ? { label: "Correlation", value: formatCorrelation(samePeriodCorrelation), note: "Same period" }
                : null,
            strongestLag !== null
                ? {
                    label: "Lead-lag",
                    value: formatLag(strongestLag, summary.strongest_lag_unit),
                    note: strongestLag > 0 ? `${firstLabel} leads` : strongestLag < 0 ? `${secondLabel} leads` : "Contemporaneous",
                }
                : null,
            strongestLagCorrelation !== null
                ? { label: "Best lag corr", value: formatCorrelation(strongestLagCorrelation), note: "Absolute strongest" }
                : null,
            overlapObservations !== null
                ? { label: "Overlap", value: formatValue(overlapObservations), note: "Aligned observations" }
                : null,
        ].filter(Boolean).slice(0, 4),
        pairCards: [
            buildSeriesCard(first),
            buildSeriesCard(second),
        ],
        insight: buildPairInsight(response, analysis, summary),
        details: [
            summary.analysis_basis ? { label: "Analysis basis", value: summary.analysis_basis } : null,
            summary.common_frequency ? { label: "Common frequency", value: summary.common_frequency } : null,
            overlapObservations !== null ? { label: "Overlap", value: `${formatValue(overlapObservations)} observations` } : null,
            { label: "Coverage", value: formatCoverage(analysis) },
            ...buildSeriesDetails([first, second]),
        ].filter(Boolean),
        actions: buildActions(response),
        warnings: analysis.warnings || [],
    };
}

function buildCrossSectionInsight(analysis, summary) {
    const leader = analysis.series_results?.[0];
    const leaderLabel = summary?.leader_label || formatSeriesLabel(leader);
    const leaderValue = leader
        ? formatValueWithUnit(leader.latest_value, leader.series.units || summary?.leader_unit)
        : "N/A";
    const hasRanking = (summary?.resolved_series_count || analysis.series_results?.length || 0) > 1;

    if (!hasRanking) {
        return {
            lead: `Point-in-time snapshot for ${leader?.series?.title || leaderLabel}.`,
            support: [
                leader?.latest_observation_date ? `${leaderValue} observed on ${formatDate(leader.latest_observation_date)}.` : `${leaderValue} observed in the latest available snapshot.`,
                `Observation basis: ${summary?.snapshot_basis || "Latest available observation"}.`,
                "Chart shows the point-in-time value rather than a time-series trend.",
            ],
        };
    }

    return {
        lead: `${leaderLabel} ranks ${summary?.rank_order || "highest"} in the current cross-section.`,
        support: [
            leader?.latest_observation_date
                ? `${leaderValue} observed on ${formatDate(leader.latest_observation_date)}.`
                : `${leaderValue} in the aligned snapshot.`,
            `Showing ${formatValue(summary?.displayed_series_count || analysis.series_results.length)} of ${formatValue(summary?.resolved_series_count || analysis.series_results.length)} resolved series.`,
            `Snapshot basis: ${summary?.snapshot_basis || "Latest available observation"}.`,
            "Bars stay sorted by the requested ranking direction.",
        ],
    };
}

function buildRankingRows(results) {
    return (results || []).slice(0, 5).map((result, index) => ({
        rank: index + 1,
        label: truncateText(formatSeriesLabel(result), 28),
        subtitle: formatSeriesSubtitle(result),
        value: formatValueWithUnit(result.latest_value, result.series.units),
        note: result.latest_observation_date ? formatDate(result.latest_observation_date) : "Latest available",
    }));
}

function buildCrossSectionDashboardModel(response) {
    const analysis = response?.result?.analysis;
    const summary = analysis?.cross_section_summary;
    const leader = analysis?.series_results?.[0];
    if (!analysis || !summary || !leader) {
        return null;
    }

    const hasRanking = (summary.resolved_series_count || analysis.series_results.length) > 1;

    return {
        mode: "cross_section",
        title: leader.series.title,
        badges: [
            formatCrossSectionScope(response.intent?.cross_section_scope),
            hasRanking ? `${humanize(summary.rank_order)} ranking` : "Snapshot",
            formatDisplaySelectionBasis(summary.display_selection_basis),
        ].filter(Boolean),
        summary: {
            label: hasRanking ? `Current ${summary.rank_order}` : "Observed value",
            value: formatValueWithUnit(leader.latest_value, leader.series.units || summary.leader_unit),
            note: leader.latest_observation_date
                ? `${summary.leader_label} | ${formatDate(leader.latest_observation_date)}`
                : summary.leader_label,
        },
        heroStats: [
            { label: "Leader", value: truncateText(summary.leader_label, 22), note: `${summary.rank_order} value` },
            summary.displayed_series_count !== null && summary.displayed_series_count !== undefined
                ? { label: "Displayed", value: formatValue(summary.displayed_series_count), note: "Series shown" }
                : null,
            summary.resolved_series_count !== null && summary.resolved_series_count !== undefined
                ? { label: "Resolved", value: formatValue(summary.resolved_series_count), note: "Series found" }
                : null,
            summary.leader_value !== null && summary.leader_value !== undefined
                ? { label: "Leader value", value: formatValueWithUnit(summary.leader_value, summary.leader_unit), note: "Snapshot leader" }
                : null,
        ].filter(Boolean).slice(0, 4),
        rankings: hasRanking ? buildRankingRows(analysis.series_results) : [],
        insight: buildCrossSectionInsight(analysis, summary),
        details: [
            { label: "Scope", value: formatCrossSectionScope(response.intent?.cross_section_scope) || "Cross section" },
            { label: "Snapshot basis", value: summary.snapshot_basis },
            { label: "Display basis", value: formatDisplaySelectionBasis(summary.display_selection_basis) || humanize(summary.display_selection_basis) },
            { label: "Rank order", value: humanize(summary.rank_order) },
            { label: "Leader series", value: leader.series.series_id },
            leader.series.source_url ? { label: "Leader source", value: "Open in FRED", href: leader.series.source_url } : null,
        ].filter(Boolean),
        actions: buildActions(response),
        warnings: analysis.warnings || [],
    };
}

export function buildDashboardModel(response) {
    if (!response?.result?.analysis?.series_results?.length) {
        return null;
    }

    if (response.intent?.task_type === TASK_TYPES.SINGLE_SERIES && response.result.analysis.series_results.length === 1) {
        return buildSingleSeriesDashboardModel(response);
    }

    if (response.intent?.task_type === TASK_TYPES.STATE_COMPARISON && response.result.analysis.series_results.length >= 2) {
        return buildStateComparisonDashboardModel(response);
    }

    if (
        (response.intent?.task_type === TASK_TYPES.MULTI_SERIES || response.intent?.task_type === TASK_TYPES.RELATIONSHIP)
        && response.result.analysis.series_results.length >= 2
    ) {
        return buildPairAnalysisDashboardModel(response);
    }

    if (response.intent?.task_type === TASK_TYPES.CROSS_SECTION) {
        return buildCrossSectionDashboardModel(response);
    }

    return null;
}
