import {
    escapeHtml,
    formatDate,
    formatPercent,
    formatValue,
    humanize,
} from "./workspace-utils.js";

export function createResultRenderer(elements) {
    const {
        results,
        answerText,
        intentSummary,
        warningList,
        metricsPanel,
        metricsGrid,
        chartPanel,
        chartTitle,
        chartSubtitle,
        chartElement,
        sourceNote,
        seriesPanel,
        seriesGrid,
        clarificationPanel,
        clarificationQuestion,
        clarificationOptions,
        clarificationHint,
        unsupportedPanel,
        unsupportedText,
    } = elements;

    function setHidden(element, hidden) {
        element.classList.toggle("hidden", hidden);
    }

    function clearResultCanvas() {
        setHidden(results, true);
        answerText.textContent = "";
        intentSummary.innerHTML = "";
        warningList.innerHTML = "";
        metricsGrid.innerHTML = "";
        seriesGrid.innerHTML = "";
        chartTitle.textContent = "";
        chartSubtitle.textContent = "";
        setHidden(chartSubtitle, true);
        sourceNote.textContent = "";
        setHidden(sourceNote, true);
        setHidden(chartPanel, true);
        setHidden(metricsPanel, true);
        setHidden(seriesPanel, true);
        if (window.Plotly) {
            window.Plotly.purge(chartElement);
        }
    }

    function extractChartTitle(response, figure) {
        const layoutTitle = figure?.layout?.title;
        if (response?.result?.chart?.title) {
            return response.result.chart.title;
        }
        if (typeof layoutTitle === "string") {
            return layoutTitle;
        }
        if (layoutTitle && typeof layoutTitle.text === "string") {
            return layoutTitle.text;
        }
        return "";
    }

    function extractChartSubtitle(response, figure) {
        if (response?.result?.chart?.subtitle) {
            return response.result.chart.subtitle;
        }

        const subtitleAnnotation = (figure?.layout?.annotations || []).find((annotation) =>
            annotation?.xref === "paper"
            && annotation?.yref === "paper"
            && annotation?.showarrow === false
            && typeof annotation?.text === "string"
        );

        return subtitleAnnotation?.text || "";
    }

    function isDateSeries(trace) {
        if (!Array.isArray(trace?.x) || trace.x.length < 2) {
            return false;
        }

        return trace.x.every((value) => typeof value === "string" && !Number.isNaN(Date.parse(value)));
    }

    function getTimeSeriesSpanYears(data) {
        let minTime = Infinity;
        let maxTime = -Infinity;
        let sawDate = false;

        for (const trace of data) {
            if (!isDateSeries(trace)) {
                return 0;
            }

            for (const value of trace.x) {
                const time = Date.parse(value);
                minTime = Math.min(minTime, time);
                maxTime = Math.max(maxTime, time);
                sawDate = true;
            }
        }

        if (!sawDate || !Number.isFinite(minTime) || !Number.isFinite(maxTime) || maxTime <= minTime) {
            return 0;
        }

        return (maxTime - minTime) / (1000 * 60 * 60 * 24 * 365.25);
    }

    function buildRangeSelectorButtons(spanYears) {
        const buttons = [];

        if (spanYears >= 3) {
            buttons.push({ count: 3, label: "3Y", step: "year", stepmode: "backward" });
        }
        if (spanYears >= 5) {
            buttons.push({ count: 5, label: "5Y", step: "year", stepmode: "backward" });
        }
        if (spanYears >= 10) {
            buttons.push({ count: 10, label: "10Y", step: "year", stepmode: "backward" });
        }
        buttons.push({ label: "All", step: "all" });

        return buttons;
    }

    function removeSubtitleAnnotation(annotations, subtitleText) {
        if (!Array.isArray(annotations) || !subtitleText) {
            return Array.isArray(annotations) ? annotations : [];
        }

        return annotations.filter((annotation) =>
            !(
                annotation?.xref === "paper"
                && annotation?.yref === "paper"
                && annotation?.showarrow === false
                && annotation?.text === subtitleText
            )
        );
    }

    function formatCandidateFrequency(value) {
        const normalized = (value || "").toUpperCase();
        return {
            D: "Daily",
            W: "Weekly",
            BW: "Biweekly",
            M: "Monthly",
            Q: "Quarterly",
            SA: "Semiannual",
            A: "Annual",
        }[normalized] || null;
    }

    function formatCandidateUnits(value) {
        const normalized = (value || "").toLowerCase();
        if (!normalized) {
            return null;
        }
        if (normalized.includes("6-month annualized")) {
            return "6M annualized";
        }
        if (normalized.includes("% chg. from yr. ago") || normalized.includes("percent change from year ago")) {
            return "YoY rate";
        }
        if (normalized.includes("annual rate") || normalized.includes("annualized")) {
            return "Annualized rate";
        }
        if (normalized.includes("index")) {
            return "Index level";
        }
        if (normalized.includes("percent")) {
            return "Percent";
        }
        return value;
    }

    function buildClarificationBadges(item) {
        const explicitBadges = Array.isArray(item.selection_badges) ? item.selection_badges.filter(Boolean) : [];
        if (explicitBadges.length > 0) {
            return explicitBadges;
        }

        const badges = [];
        const frequencyBadge = formatCandidateFrequency(item.frequency);
        const unitBadge = formatCandidateUnits(item.units);
        if (frequencyBadge) {
            badges.push(frequencyBadge);
        }
        if (unitBadge) {
            badges.push(unitBadge);
        }
        if (item.seasonal_adjustment) {
            badges.push(item.seasonal_adjustment);
        }
        return badges.slice(0, 3);
    }

    function renderIntent(intent) {
        const geographies = (intent.geographies || []).map((item) => item.name).filter(Boolean).join(", ");
        const indicators = (intent.indicators || []).map(humanize).join(", ");
        const items = [
            ["Task", humanize(intent.task_type)],
            ["Transform", humanize(intent.transform)],
            ["Comparison", humanize(intent.comparison_mode)],
            ["Start", intent.start_date ? formatDate(intent.start_date) : null],
            ["End", intent.end_date ? formatDate(intent.end_date) : "Latest available"],
            ["Geographies", geographies || null],
            ["Indicators", indicators || null],
        ].filter(([, value]) => value);

        intentSummary.innerHTML = items
            .map(
                ([label, value]) => `
                    <div>
                        <dt>${escapeHtml(label)}</dt>
                        <dd>${escapeHtml(value)}</dd>
                    </div>
                `,
            )
            .join("");
    }

    function renderWarnings(warnings) {
        if (!warnings || warnings.length === 0) {
            warningList.innerHTML = "";
            return;
        }

        warningList.innerHTML = warnings
            .map((warning) => `<span class="warning-chip">${escapeHtml(warning)}</span>`)
            .join("");
    }

    function renderDerivedMetrics(metrics) {
        if (!metrics || metrics.length === 0) {
            metricsGrid.innerHTML = "";
            setHidden(metricsPanel, true);
            return;
        }

        metricsGrid.innerHTML = metrics
            .map((metric) => {
                const unit = metric.unit ? ` ${escapeHtml(metric.unit)}` : "";
                return `
                    <article class="metric-card">
                        <p class="metric-card-label">${escapeHtml(humanize(metric.name))}</p>
                        <p class="metric-card-value">${escapeHtml(formatValue(metric.value))}${unit}</p>
                        ${metric.description ? `<p class="metric-card-description">${escapeHtml(metric.description)}</p>` : ""}
                    </article>
                `;
            })
            .join("");
        setHidden(metricsPanel, false);
    }

    function renderChart(figure, response) {
        if (!figure || !window.Plotly) {
            setHidden(chartPanel, true);
            return;
        }

        const chartTitleText = extractChartTitle(response, figure);
        const chartSubtitleText = extractChartSubtitle(response, figure);
        const data = (figure.data || []).map((trace) => ({ ...trace }));
        const spanYears = getTimeSeriesSpanYears(data);
        const showRangeControls = spanYears >= 4;
        const showLegend = data.length > 1;

        chartTitle.textContent = chartTitleText;
        chartSubtitle.textContent = chartSubtitleText;
        setHidden(chartSubtitle, !chartSubtitleText);
        setHidden(chartPanel, false);

        const layout = {
            ...figure.layout,
            paper_bgcolor: "rgba(0, 0, 0, 0)",
            plot_bgcolor: "rgba(0, 0, 0, 0)",
            hovermode: "x unified",
            hoverdistance: 80,
            spikedistance: -1,
            margin: {
                l: 64,
                r: 18,
                t: 20,
                b: showRangeControls ? 118 : (showLegend ? 86 : 56),
            },
            font: {
                family: '"IBM Plex Sans", "Segoe UI", sans-serif',
                color: "#15212f",
            },
            showlegend: showLegend,
            hoverlabel: {
                bgcolor: "#ffffff",
                bordercolor: "rgba(21, 33, 47, 0.16)",
                font: {
                    family: '"IBM Plex Sans", "Segoe UI", sans-serif',
                    color: "#15212f",
                },
                namelength: 56,
            },
            legend: showLegend ? {
                orientation: "h",
                yanchor: "top",
                y: -0.2,
                xanchor: "left",
                x: 0,
                font: {
                    size: 12,
                    color: "#435365",
                },
            } : undefined,
            annotations: removeSubtitleAnnotation(figure.layout?.annotations, chartSubtitleText),
            xaxis: {
                ...figure.layout?.xaxis,
                gridcolor: "rgba(21, 33, 47, 0.08)",
                zeroline: false,
                automargin: true,
                showspikes: true,
                spikemode: "across",
                spikecolor: "rgba(21, 33, 47, 0.16)",
                spikethickness: 1,
                tickfont: {
                    color: "#435365",
                },
                tickformatstops: showRangeControls ? [
                    { dtickrange: [null, 86400000 * 31], value: "%b %Y" },
                    { dtickrange: [86400000 * 31, 86400000 * 366], value: "%b %Y" },
                    { dtickrange: [86400000 * 366, null], value: "%Y" },
                ] : undefined,
                rangeselector: showRangeControls ? {
                    x: 0,
                    y: 1.14,
                    xanchor: "left",
                    yanchor: "bottom",
                    bgcolor: "rgba(255, 255, 255, 0.94)",
                    activecolor: "rgba(13, 115, 119, 0.14)",
                    bordercolor: "rgba(21, 33, 47, 0.1)",
                    borderwidth: 1,
                    buttons: buildRangeSelectorButtons(spanYears),
                } : undefined,
                rangeslider: showRangeControls ? {
                    visible: true,
                    bgcolor: "rgba(21, 33, 47, 0.04)",
                    bordercolor: "rgba(21, 33, 47, 0.1)",
                    thickness: 0.1,
                } : { visible: false },
            },
            yaxis: {
                ...figure.layout?.yaxis,
                gridcolor: "rgba(21, 33, 47, 0.08)",
                zeroline: false,
                automargin: true,
                tickfont: {
                    color: "#435365",
                },
            },
        };

        delete layout.title;
        delete layout.width;
        delete layout.height;

        window.Plotly.react(chartElement, data, layout, {
            responsive: true,
            displayModeBar: false,
            scrollZoom: false,
        }).then(() => {
            if (window.Plotly?.Plots?.resize) {
                window.requestAnimationFrame(() => {
                    window.Plotly.Plots.resize(chartElement);
                });
            }
        });

        sourceNote.textContent = response.result?.chart?.source_note || "";
        setHidden(sourceNote, !sourceNote.textContent);
    }

    function renderSeriesResults(seriesResults) {
        if (!seriesResults || seriesResults.length === 0) {
            setHidden(seriesPanel, true);
            seriesGrid.innerHTML = "";
            return;
        }

        seriesGrid.innerHTML = seriesResults
            .map((item) => {
                const series = item.series;
                return `
                    <article class="series-card">
                        <header>
                            <h3>${escapeHtml(series.title)}</h3>
                            <div class="series-badges">
                                <span class="badge">${escapeHtml(series.series_id)}</span>
                                <span class="badge">${escapeHtml(series.frequency)}</span>
                                ${series.seasonal_adjustment ? `<span class="badge">${escapeHtml(series.seasonal_adjustment)}</span>` : ""}
                            </div>
                        </header>
                        <div class="series-headline">
                            <p class="series-headline-value">${escapeHtml(formatValue(item.latest_value))} <span class="series-headline-unit">${escapeHtml(series.units)}</span></p>
                            <p class="series-headline-date">as of ${escapeHtml(formatDate(item.latest_observation_date))}</p>
                        </div>
                        <div class="metric-list">
                            <div class="metric-row">
                                <span class="metric-label">Total growth</span>
                                <span class="metric-value">${escapeHtml(formatPercent(item.total_growth_pct))}</span>
                            </div>
                            <div class="metric-row">
                                <span class="metric-label">CAGR</span>
                                <span class="metric-value">${escapeHtml(formatPercent(item.compound_annual_growth_rate_pct))}</span>
                            </div>
                        </div>
                        <details class="series-secondary">
                            <summary class="series-secondary-toggle">More details</summary>
                            <div class="metric-list series-secondary-body">
                                <div class="metric-row">
                                    <span class="metric-label">Geography</span>
                                    <span class="metric-value">${escapeHtml(series.geography)}</span>
                                </div>
                                ${item.analysis_basis ? `
                                <div class="metric-row">
                                    <span class="metric-label">Analysis basis</span>
                                    <span class="metric-value">${escapeHtml(item.analysis_basis)}</span>
                                </div>
                                ` : ""}
                                ${series.resolution_reason ? `
                                <div class="metric-row">
                                    <span class="metric-label">Resolution</span>
                                    <span class="metric-value metric-value-secondary">${escapeHtml(series.resolution_reason)}</span>
                                </div>
                                ` : ""}
                            </div>
                        </details>
                        <a class="resource-link" href="${escapeHtml(series.source_url)}" target="_blank" rel="noreferrer">Open in FRED</a>
                    </article>
                `;
            })
            .join("");
        setHidden(seriesPanel, false);
    }

    function renderResultPayload(response) {
        if (!response?.result) {
            clearResultCanvas();
            return;
        }

        setHidden(results, false);
        answerText.textContent = response.answer_text || "";
        renderIntent(response.intent || {});
        renderWarnings(response.result?.analysis?.warnings || []);
        renderDerivedMetrics(response.result?.analysis?.derived_metrics || []);
        renderChart(response.plotly_figure, response);
        renderSeriesResults(response.result?.analysis?.series_results || []);
    }

    function clearClarificationPanel() {
        clarificationQuestion.textContent = "";
        clarificationOptions.innerHTML = "";
        clarificationHint.textContent = "Choose one, or keep typing to narrow it down.";
        setHidden(clarificationPanel, true);
    }

    function renderClarificationPanel(revision, selectedSeriesId) {
        if (!revision || revision.response?.status !== "needs_clarification") {
            clearClarificationPanel();
            return;
        }

        const candidates = (revision.response.candidate_series || []).slice(0, 4);
        clarificationQuestion.textContent = revision.response.answer_text || "Pick the series you meant.";
        clarificationOptions.innerHTML = candidates
            .map((item) => {
                const badges = buildClarificationBadges(item);
                const label = item.selection_label || item.title;
                const showOfficialTitle = Boolean(item.selection_label && item.selection_label !== item.title);
                return `
                    <button
                        type="button"
                        class="clarification-option ${selectedSeriesId === item.series_id ? "is-active" : ""}"
                        data-series-id="${escapeHtml(item.series_id)}"
                    >
                        <div class="clarification-option-header">
                            <span class="clarification-option-label">${escapeHtml(label)}</span>
                            <span class="clarification-option-series-id">FRED: ${escapeHtml(item.series_id)}</span>
                        </div>
                        ${showOfficialTitle ? `<span class="clarification-option-title">${escapeHtml(item.title)}</span>` : ""}
                        ${badges.length ? `
                            <div class="clarification-option-badges">
                                ${badges.map((badge) => `<span class="clarification-option-badge">${escapeHtml(badge)}</span>`).join("")}
                            </div>
                        ` : ""}
                        ${item.selection_hint ? `<span class="clarification-option-hint">${escapeHtml(item.selection_hint)}</span>` : ""}
                    </button>
                `;
            })
            .join("");
        clarificationHint.textContent = candidates.length > 0
            ? "Choose one, or keep typing to narrow it down."
            : "No confident series matches yet. Keep typing more specifically or enter a FRED series ID.";
        setHidden(clarificationPanel, false);
    }

    function renderUnsupportedPanel(revision) {
        if (!revision || revision.response?.status !== "unsupported") {
            unsupportedText.textContent = "";
            setHidden(unsupportedPanel, true);
            return;
        }

        unsupportedText.textContent = revision.response.answer_text || "";
        setHidden(unsupportedPanel, false);
    }

    function getClarificationButtons() {
        return Array.from(clarificationOptions.querySelectorAll(".clarification-option"));
    }

    return {
        clearClarificationPanel,
        clearResultCanvas,
        getClarificationButtons,
        renderClarificationPanel,
        renderResultPayload,
        renderUnsupportedPanel,
    };
}
