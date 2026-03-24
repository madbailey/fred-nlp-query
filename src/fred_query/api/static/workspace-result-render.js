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
        sourceNote.textContent = "";
        setHidden(chartPanel, true);
        setHidden(metricsPanel, true);
        setHidden(seriesPanel, true);
        if (window.Plotly) {
            window.Plotly.purge(chartElement);
        }
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

        const layout = {
            ...figure.layout,
            paper_bgcolor: "rgba(0, 0, 0, 0)",
            plot_bgcolor: "rgba(0, 0, 0, 0)",
            hovermode: "x unified",
            margin: { l: 58, r: 24, t: 76, b: 52 },
            font: {
                family: '"IBM Plex Sans", "Segoe UI", sans-serif',
                color: "#15212f",
            },
            legend: {
                orientation: "h",
                yanchor: "bottom",
                y: 1.02,
                x: 0,
            },
            xaxis: {
                ...figure.layout?.xaxis,
                gridcolor: "rgba(21, 33, 47, 0.08)",
                zeroline: false,
            },
            yaxis: {
                ...figure.layout?.yaxis,
                gridcolor: "rgba(21, 33, 47, 0.08)",
                zeroline: false,
            },
        };

        window.Plotly.react(chartElement, figure.data || [], layout, {
            responsive: true,
            displayModeBar: false,
        });

        sourceNote.textContent = response.result?.chart?.source_note || "";
        setHidden(chartPanel, false);
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
                            <div class="series-badges">
                                <span class="badge">${escapeHtml(series.series_id)}</span>
                                <span class="badge">${escapeHtml(series.frequency)}</span>
                                ${series.seasonal_adjustment ? `<span class="badge">${escapeHtml(series.seasonal_adjustment)}</span>` : ""}
                            </div>
                            <h3>${escapeHtml(series.title)}</h3>
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

        answerText.textContent = response.answer_text || "";
        renderIntent(response.intent || {});
        renderWarnings(response.result?.analysis?.warnings || []);
        renderDerivedMetrics(response.result?.analysis?.derived_metrics || []);
        renderChart(response.plotly_figure, response);
        renderSeriesResults(response.result?.analysis?.series_results || []);
        setHidden(results, false);
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
            .map((item) => `
                <button
                    type="button"
                    class="clarification-option ${selectedSeriesId === item.series_id ? "is-active" : ""}"
                    data-series-id="${escapeHtml(item.series_id)}"
                >
                    <span class="clarification-option-title">${escapeHtml(item.title)}</span>
                    <span class="clarification-option-meta">${escapeHtml([item.series_id, item.frequency, item.units].filter(Boolean).join(" / "))}</span>
                </button>
            `)
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
