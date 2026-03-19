const queryForm = document.getElementById("query-form");
const queryInput = document.getElementById("query-input");
const submitButton = document.getElementById("submit-button");
const resetSessionButton = document.getElementById("reset-session-button");
const sessionRow = document.getElementById("session-row");
const sessionSummary = document.getElementById("session-summary");
const suggestionsContainer = document.querySelector(".suggestions");
const suggestionButtons = Array.from(document.querySelectorAll(".suggestion"));
const clarificationInline = document.getElementById("clarification-inline");
const clarificationQuestion = document.getElementById("clarification-question");
const clarificationOptions = document.getElementById("clarification-options");
const clarificationHint = document.getElementById("clarification-hint");
const statusRow = document.getElementById("status-row");
const statusPill = document.getElementById("status-pill");
const statusText = document.getElementById("status-text");
const errorBanner = document.getElementById("error-banner");
const conversationThread = document.getElementById("conversation-thread");
const results = document.getElementById("results");
const answerText = document.getElementById("answer-text");
const intentSummary = document.getElementById("intent-summary");
const warningList = document.getElementById("warning-list");
const metricsPanel = document.getElementById("metrics-panel");
const metricsGrid = document.getElementById("metrics-grid");
const chartPanel = document.getElementById("chart-panel");
const chartElement = document.getElementById("chart");
const sourceNote = document.getElementById("source-note");
const seriesPanel = document.getElementById("series-panel");
const seriesGrid = document.getElementById("series-grid");

const SESSION_STORAGE_KEY = "fred-query-session-id";
const SESSION_HISTORY_KEY = "fred-query-history";

let pendingClarification = null;
let selectedClarificationSeriesId = null;
let activeSessionId = loadStoredSessionId();
let conversationHistory = loadStoredHistory();

function loadStoredSessionId() {
    try {
        return window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    } catch {
        return null;
    }
}

function loadStoredHistory() {
    try {
        const raw = window.sessionStorage.getItem(SESSION_HISTORY_KEY);
        return raw ? JSON.parse(raw) : [];
    } catch {
        return [];
    }
}

function saveHistory() {
    try {
        window.sessionStorage.setItem(SESSION_HISTORY_KEY, JSON.stringify(conversationHistory));
    } catch {
        return;
    }
}

function truncateToFirstSentence(text, maxLength = 160) {
    if (!text) {
        return "";
    }

    const sentenceEnd = text.search(/[.!?]\s/);
    if (sentenceEnd !== -1 && sentenceEnd < maxLength) {
        return text.slice(0, sentenceEnd + 1);
    }

    if (text.length <= maxLength) {
        return text;
    }

    return `${text.slice(0, maxLength).trimEnd()}\u2026`;
}

function addToHistory(query, answerSnippet) {
    conversationHistory.push({ query, answer: truncateToFirstSentence(answerSnippet) });
    saveHistory();
}

function clearHistory() {
    conversationHistory = [];
    try {
        window.sessionStorage.removeItem(SESSION_HISTORY_KEY);
    } catch {
        return;
    }
}

function setActiveSessionId(sessionId) {
    activeSessionId = sessionId || null;
    try {
        if (activeSessionId) {
            window.sessionStorage.setItem(SESSION_STORAGE_KEY, activeSessionId);
        } else {
            window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
        }
    } catch {
        return;
    }
}

function updateSessionUI() {
    const hasSession = conversationHistory.length > 0;
    const hero = document.querySelector(".hero");

    setHidden(sessionRow, !hasSession);
    if (hasSession) {
        const lastQuery = conversationHistory[conversationHistory.length - 1].query;
        sessionSummary.textContent = `Following up on: ${lastQuery}`;
        queryInput.placeholder = "Ask a follow-up, e.g. \u201CNow show me year-over-year change\u201D or \u201CHow about since 2015?\u201D";
    } else {
        queryInput.placeholder = "e.g. What is the relationship between Brent crude oil prices and inflation?";
    }

    hero.classList.toggle("compact", hasSession);
    setHidden(suggestionsContainer, hasSession);
}

function setHidden(element, hidden) {
    element.classList.toggle("hidden", hidden);
}

function humanize(value) {
    if (!value) {
        return "";
    }

    return String(value)
        .replace(/_/g, " ")
        .replace(/\b\w/g, (match) => match.toUpperCase());
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function formatDate(value) {
    if (!value) {
        return "N/A";
    }

    return new Intl.DateTimeFormat("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
    }).format(new Date(`${value}T00:00:00`));
}

function formatValue(value) {
    if (typeof value === "string" && Number.isNaN(Number(value))) {
        return value;
    }

    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "N/A";
    }

    const numeric = Number(value);
    const formatter = Math.abs(numeric) >= 10000
        ? new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 })
        : new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
    return formatter.format(numeric);
}

function formatPercent(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "N/A";
    }

    return `${formatValue(value)}%`;
}

function clearError() {
    errorBanner.textContent = "";
    setHidden(errorBanner, true);
}

function showError(message) {
    errorBanner.textContent = message;
    setHidden(errorBanner, false);
}

function getClarificationButtons() {
    return Array.from(clarificationOptions.querySelectorAll(".clarification-option"));
}

function extractErrorMessage(payload, fallbackMessage) {
    if (payload?.error?.message) {
        return payload.error.message;
    }

    if (typeof payload?.detail === "string" && payload.detail) {
        return payload.detail;
    }

    if (Array.isArray(payload?.detail) && payload.detail.length > 0) {
        const messages = payload.detail
            .map((item) => item?.msg)
            .filter(Boolean);
        if (messages.length > 0) {
            return messages.join(" ");
        }
    }

    return fallbackMessage;
}

function clearClarification() {
    pendingClarification = null;
    selectedClarificationSeriesId = null;
    clarificationQuestion.textContent = "";
    clarificationOptions.innerHTML = "";
    clarificationHint.textContent = "Choose one, or keep typing to narrow it down.";
    setHidden(clarificationInline, true);
}

function clearResults({ keepClarification = false } = {}) {
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
    if (!keepClarification) {
        clearClarification();
    }
    if (window.Plotly) {
        window.Plotly.purge(chartElement);
    }
}

function updateStatus(state, message) {
    if (!state && !message) {
        setHidden(statusRow, true);
        statusPill.textContent = "";
        statusPill.dataset.state = "";
        statusText.textContent = "";
        return;
    }

    const labels = {
        working: "Working",
        completed: "Completed",
        needs_clarification: "Clarify",
        unsupported: "Unsupported",
    };

    statusPill.textContent = labels[state] || humanize(state);
    statusPill.dataset.state = state || "";
    statusText.textContent = message || "";
    setHidden(statusRow, false);
}

function setLoading(isLoading) {
    submitButton.disabled = isLoading;
    queryInput.disabled = isLoading;
    resetSessionButton.disabled = isLoading;
    suggestionButtons.forEach((button) => {
        button.disabled = isLoading;
    });
    getClarificationButtons().forEach((button) => {
        button.disabled = isLoading;
    });
    submitButton.textContent = isLoading ? "Running..." : "Ask";
    if (isLoading) {
        updateStatus(
            "working",
            "Parsing the query, resolving series against FRED, and assembling a chart-ready response.",
        );
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
            color: "#1a1a1a",
        },
        legend: {
            orientation: "h",
            yanchor: "bottom",
            y: 1.02,
            x: 0,
        },
        xaxis: {
            ...figure.layout?.xaxis,
            gridcolor: "rgba(23, 48, 68, 0.08)",
            zeroline: false,
        },
        yaxis: {
            ...figure.layout?.yaxis,
            gridcolor: "rgba(23, 48, 68, 0.08)",
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
                        <p class="series-headline-value">${escapeHtml(formatValue(item.latest_value))} <span style="font-size:0.72rem;font-weight:400;color:var(--muted)">${escapeHtml(series.units)}</span></p>
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
                        <div class="metric-list" style="margin-top:8px">
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
                                <span class="metric-value" style="font-weight:400">${escapeHtml(series.resolution_reason)}</span>
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

function formatClarificationMeta(candidate) {
    return [candidate.series_id, candidate.frequency, candidate.units]
        .filter(Boolean)
        .join(" / ");
}

function renderClarificationOptions(response, query) {
    const candidates = (response.candidate_series || []).slice(0, 4);
    if (response.status !== "needs_clarification" || !query) {
        clearClarification();
        return;
    }

    pendingClarification = {
        query,
        candidates,
        question: response.answer_text || "Pick the series you meant.",
        selectedSeriesIds: Array.isArray(response.intent?.series_ids) ? [...response.intent.series_ids] : [],
        targetIndex: Number.isInteger(response.intent?.clarification_target_index)
            ? response.intent.clarification_target_index
            : 0,
    };
    clarificationQuestion.textContent = pendingClarification.question;
    clarificationOptions.innerHTML = candidates
        .map((item) => `
            <button
                type="button"
                class="clarification-option ${selectedClarificationSeriesId === item.series_id ? "is-active" : ""}"
                data-series-id="${escapeHtml(item.series_id)}"
            >
                <span class="clarification-option-title">${escapeHtml(item.title)}</span>
                <span class="clarification-option-meta">${escapeHtml(formatClarificationMeta(item))}</span>
            </button>
        `)
        .join("");
    clarificationHint.textContent = candidates.length > 0
        ? "Choose one, or keep typing to narrow it down."
        : "No confident series matches yet. Keep typing more specifically or enter a FRED series ID.";
    setHidden(clarificationInline, false);
}

function renderConversationThread() {
    if (conversationHistory.length === 0) {
        setHidden(conversationThread, true);
        conversationThread.innerHTML = "";
        return;
    }

    const previousTurns = conversationHistory.slice(0, -1);
    if (previousTurns.length === 0) {
        setHidden(conversationThread, true);
        conversationThread.innerHTML = "";
        return;
    }

    conversationThread.innerHTML = previousTurns
        .map((turn) => `
            <div class="thread-turn">
                <p class="thread-query">${escapeHtml(turn.query)}</p>
                <p class="thread-answer">${escapeHtml(turn.answer)}</p>
            </div>
        `)
        .join("");
    setHidden(conversationThread, false);
}

function renderResponse(response, query) {
    const isClarification = response.status === "needs_clarification";

    if (isClarification) {
        updateStatus(response.status, "Which series did you mean?");
    } else if (response.status === "unsupported") {
        updateStatus(response.status, "This query type isn't supported yet.");
    } else {
        updateStatus(null, "");
    }

    setHidden(results, isClarification);
    if (!isClarification) {
        answerText.textContent = response.answer_text || "";
        renderIntent(response.intent || {});
        renderWarnings(response.result?.analysis?.warnings || []);
        renderDerivedMetrics(response.result?.analysis?.derived_metrics || []);
        renderChart(response.plotly_figure, response);
        renderSeriesResults(response.result?.analysis?.series_results || []);
    }
    renderClarificationOptions(response, query);
}

async function submitQuery({ query, selectedSeriesIds = [], preserveCurrentResults = false }) {
    clearError();
    if (!preserveCurrentResults) {
        clearResults();
    }
    setLoading(true);

    try {
        const response = await fetch("/api/ask", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                query,
                session_id: activeSessionId,
                selected_series_id: selectedSeriesIds.find((value) => Boolean(value)) || null,
                selected_series_ids: selectedSeriesIds,
            }),
        });

        const text = await response.text();
        let payload = {};
        if (text) {
            try {
                payload = JSON.parse(text);
            } catch {
                throw new Error(text);
            }
        }

        if (!response.ok) {
            throw new Error(extractErrorMessage(payload, "The query request failed."));
        }

        if (payload.session_id) {
            setActiveSessionId(payload.session_id);
        }
        if (payload.status === "completed" || payload.status === "unsupported") {
            addToHistory(query, payload.answer_text || "");
        }
        renderConversationThread();
        updateSessionUI();
        renderResponse(payload, query);
        if (payload.status !== "needs_clarification") {
            queryInput.value = "";
        }
        if (!results.classList.contains("hidden")) {
            results.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    } catch (error) {
        showError(error instanceof Error ? error.message : "Unexpected error.");
        updateStatus(null, "");
    } finally {
        setLoading(false);
    }
}

async function handleSubmit(event) {
    event.preventDefault();
    const query = queryInput.value.trim();

    if (!query) {
        showError("Enter a FRED question first.");
        return;
    }

    await submitQuery({ query });
}

function resetConversation() {
    setActiveSessionId(null);
    clearHistory();
    clearError();
    clearResults();
    updateStatus(null, "");
    renderConversationThread();
    updateSessionUI();
}

queryForm.addEventListener("submit", handleSubmit);
resetSessionButton.addEventListener("click", () => {
    resetConversation();
    queryInput.focus();
});
suggestionButtons.forEach((button) => {
    button.addEventListener("click", () => {
        queryInput.value = button.dataset.query || "";
        queryForm.requestSubmit();
    });
});
clarificationOptions.addEventListener("click", (event) => {
    const option = event.target.closest(".clarification-option");
    if (!option || !pendingClarification) {
        return;
    }

    selectedClarificationSeriesId = option.dataset.seriesId || null;
    renderClarificationOptions(
        {
            status: "needs_clarification",
            answer_text: pendingClarification.question,
            candidate_series: pendingClarification.candidates,
        },
        pendingClarification.query,
    );
    submitQuery({
        query: pendingClarification.query,
        selectedSeriesIds: (() => {
            const selections = [...pendingClarification.selectedSeriesIds];
            selections[pendingClarification.targetIndex] = selectedClarificationSeriesId;
            return selections;
        })(),
        preserveCurrentResults: true,
    });
});
queryInput.addEventListener("input", () => {
    if (!pendingClarification) {
        return;
    }

    if (queryInput.value.trim() !== pendingClarification.query) {
        clearClarification();
    }
});

renderConversationThread();
updateSessionUI();
