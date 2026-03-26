import { createResultRenderer } from "./workspace-result-render.js";
import {
    STATUS_LABELS,
    escapeHtml,
    formatRevisionStatus,
    humanize,
    truncateText,
} from "./workspace-utils.js";

const WORKSPACE_STORAGE_KEY = "fred-query-workspace-v1";

export function mountWorkspaceApp() {
    const elements = {
        entryView: document.getElementById("entry-view"),
        workspaceView: document.getElementById("workspace-view"),
        entryComposerSlot: document.getElementById("entry-composer-slot"),
        workspaceComposerSlot: document.getElementById("workspace-composer-slot"),
        composerCard: document.getElementById("composer-card"),
        queryForm: document.getElementById("query-form"),
        queryInput: document.getElementById("query-input"),
        submitButton: document.getElementById("submit-button"),
        resetSessionButton: document.getElementById("reset-session-button"),
        suggestionsContainer: document.querySelector(".suggestions"),
        suggestionButtons: Array.from(document.querySelectorAll(".suggestion")),
        composerContext: document.getElementById("composer-context"),
        workspaceSidebar: document.querySelector(".workspace-sidebar"),
        workspaceTitle: document.getElementById("workspace-title"),
        workspaceSubtitle: document.getElementById("workspace-subtitle"),
        revisionSection: document.querySelector(".sidebar-section"),
        revisionCount: document.getElementById("revision-count"),
        revisionList: document.getElementById("revision-list"),
        workspaceScroll: document.getElementById("workspace-scroll"),
        activeResultTitle: document.getElementById("active-result-title"),
        activeResultMeta: document.getElementById("active-result-meta"),
        workspaceContextBanner: document.getElementById("workspace-context-banner"),
        emptyStatePanel: document.getElementById("empty-state-panel"),
        statusRow: document.getElementById("status-row"),
        statusPill: document.getElementById("status-pill"),
        statusText: document.getElementById("status-text"),
        errorBanner: document.getElementById("error-banner"),
        results: document.getElementById("results"),
        answerText: document.getElementById("answer-text"),
        intentSummary: document.getElementById("intent-summary"),
        warningList: document.getElementById("warning-list"),
        followUpPanel: document.getElementById("follow-up-panel"),
        followUpList: document.getElementById("follow-up-list"),
        metricsPanel: document.getElementById("metrics-panel"),
        metricsGrid: document.getElementById("metrics-grid"),
        chartPanel: document.getElementById("chart-panel"),
        chartTitle: document.getElementById("chart-title"),
        chartSubtitle: document.getElementById("chart-subtitle"),
        chartElement: document.getElementById("chart"),
        sourceNote: document.getElementById("source-note"),
        seriesPanel: document.getElementById("series-panel"),
        seriesGrid: document.getElementById("series-grid"),
        clarificationPanel: document.getElementById("clarification-panel"),
        clarificationQuestion: document.getElementById("clarification-question"),
        clarificationOptions: document.getElementById("clarification-options"),
        clarificationHint: document.getElementById("clarification-hint"),
        unsupportedPanel: document.getElementById("unsupported-panel"),
        unsupportedText: document.getElementById("unsupported-text"),
    };

    const resultRenderer = createResultRenderer(elements);
    let workspace = loadWorkspace();
    let isLoading = false;
    let selectedClarificationSeriesId = null;

    function setHidden(element, hidden) {
        element.classList.toggle("hidden", hidden);
    }

    function createEmptyWorkspace() {
        return { sessionId: null, title: "", revisions: [], activeRevisionId: null };
    }

    function loadWorkspace() {
        try {
            const raw = window.localStorage.getItem(WORKSPACE_STORAGE_KEY);
            return raw ? normalizeWorkspace(JSON.parse(raw)) : createEmptyWorkspace();
        } catch {
            return createEmptyWorkspace();
        }
    }

    function saveWorkspace() {
        try {
            if (!workspace.revisions.length && !workspace.sessionId) {
                window.localStorage.removeItem(WORKSPACE_STORAGE_KEY);
                return;
            }
            window.localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(workspace));
        } catch {
            return;
        }
    }

    function normalizeWorkspace(value) {
        const revisions = Array.isArray(value?.revisions)
            ? value.revisions.map(normalizeRevision).filter(Boolean)
            : [];
        const activeRevisionId = revisions.some((revision) => revision.id === value?.activeRevisionId)
            ? value.activeRevisionId
            : (revisions[revisions.length - 1]?.id || null);
        return {
            sessionId: typeof value?.sessionId === "string" ? value.sessionId : null,
            title: typeof value?.title === "string" ? value.title : "",
            revisions,
            activeRevisionId,
        };
    }

    function normalizeRevision(value) {
        if (!value || typeof value !== "object" || typeof value.id !== "string" || typeof value.prompt !== "string") {
            return null;
        }
        return {
            id: value.id,
            prompt: value.prompt,
            response: value.response,
            status: typeof value.status === "string" ? value.status : value.response?.status || "completed",
            label: typeof value.label === "string" ? value.label : deriveRevisionLabel(value.response, value.prompt),
            createdAt: typeof value.createdAt === "string" ? value.createdAt : new Date().toISOString(),
            baseRevisionId: typeof value.baseRevisionId === "string" ? value.baseRevisionId : null,
        };
    }

    function deriveRevisionLabel(response, prompt) {
        if (!response) {
            return truncateText(prompt, 56);
        }
        if (response.status === "needs_clarification") {
            return "Needs clarification";
        }
        if (response.status === "unsupported") {
            return humanize(response.intent?.task_type) || "Unsupported request";
        }
        const seriesResults = response.result?.analysis?.series_results || [];
        if (seriesResults.length === 1) {
            return seriesResults[0].series?.title || truncateText(prompt, 56);
        }
        if (seriesResults.length >= 2) {
            const first = seriesResults[0].series?.title || seriesResults[0].series?.series_id || "Series 1";
            const second = seriesResults[1].series?.title || seriesResults[1].series?.series_id || "Series 2";
            return `${truncateText(first, 28)} vs ${truncateText(second, 28)}`;
        }
        return response.plotly_figure?.layout?.title?.text || humanize(response.intent?.task_type) || truncateText(prompt, 56);
    }

    function findRevisionById(revisionId) {
        return workspace.revisions.find((revision) => revision.id === revisionId) || null;
    }

    function getLatestRevision() {
        return workspace.revisions[workspace.revisions.length - 1] || null;
    }

    function getActiveRevision() {
        return findRevisionById(workspace.activeRevisionId) || getLatestRevision();
    }

    function getRevisionIndex(revisionId) {
        return workspace.revisions.findIndex((revision) => revision.id === revisionId);
    }

    function getReferenceRevision(revision) {
        let current = revision;
        while (current) {
            if (current.response?.status === "completed" && current.response?.result) {
                return current;
            }
            current = findRevisionById(current.baseRevisionId);
        }
        return null;
    }

    function updateStatus(state, message) {
        if (!state && !message) {
            setHidden(elements.statusRow, true);
            elements.statusPill.textContent = "";
            elements.statusPill.dataset.state = "";
            elements.statusText.textContent = "";
            return;
        }
        elements.statusPill.textContent = STATUS_LABELS[state] || humanize(state);
        elements.statusPill.dataset.state = state || "";
        elements.statusText.textContent = message || "";
        setHidden(elements.statusRow, false);
    }

    function showError(message) {
        elements.errorBanner.textContent = message;
        setHidden(elements.errorBanner, false);
    }

    function clearError() {
        elements.errorBanner.textContent = "";
        setHidden(elements.errorBanner, true);
    }

    function syncStatus() {
        if (isLoading) {
            updateStatus("working", "Processing query...");
            return;
        }
        const activeRevision = getActiveRevision();
        if (activeRevision?.response?.status === "needs_clarification") {
            updateStatus("needs_clarification", "Pick a series to continue.");
            return;
        }
        if (activeRevision?.response?.status === "unsupported") {
            updateStatus("unsupported", "This type of question isn't supported yet.");
            return;
        }
        updateStatus(null, "");
    }

    function renderRevisionList() {
        if (!workspace.revisions.length) {
            elements.revisionCount.textContent = "";
            elements.revisionList.innerHTML = '<p class="revision-empty">No revisions yet. Your first result will open the workspace.</p>';
            return;
        }

        const activeRevision = getActiveRevision();
        elements.revisionCount.textContent = `${workspace.revisions.length} total`;
        elements.revisionList.innerHTML = [...workspace.revisions]
            .map((revision, index) => ({ revision, index }))
            .reverse()
            .map(({ revision, index }) => `
                <button type="button" class="revision-item ${activeRevision?.id === revision.id ? "is-active" : ""}" data-revision-id="${escapeHtml(revision.id)}">
                    <div class="revision-item-top">
                        <span class="revision-step">R${index + 1}</span>
                        <span class="revision-status-chip" data-status="${escapeHtml(revision.status)}">${escapeHtml(formatRevisionStatus(revision.status))}</span>
                    </div>
                    <p class="revision-item-label">${escapeHtml(revision.label)}</p>
                    <p class="revision-item-prompt">${escapeHtml(revision.prompt)}</p>
                </button>
            `)
            .join("");
    }

    function renderActiveRevision() {
        const activeRevision = getActiveRevision();
        if (!activeRevision) {
            elements.activeResultTitle.textContent = "Result workspace";
            elements.activeResultMeta.textContent = "";
            resultRenderer.clearClarificationPanel();
            resultRenderer.renderUnsupportedPanel(null);
            resultRenderer.clearResultCanvas();
            setHidden(elements.workspaceContextBanner, true);
            setHidden(elements.emptyStatePanel, false);
            return;
        }

        const referenceRevision = getReferenceRevision(activeRevision);
        const activeIndex = getRevisionIndex(activeRevision.id) + 1;
        const latestRevision = getLatestRevision();
        elements.activeResultTitle.textContent = activeRevision.label;
        elements.activeResultMeta.textContent = `Revision ${activeIndex} of ${workspace.revisions.length} · ${formatRevisionStatus(activeRevision.status)}${activeRevision.response?.intent?.task_type ? ` · ${humanize(activeRevision.response.intent.task_type)}` : ""}`;
        if (activeRevision.response?.status === "needs_clarification" && referenceRevision) {
            elements.workspaceContextBanner.textContent = "Showing the previous result while this revision needs clarification.";
            setHidden(elements.workspaceContextBanner, false);
        } else if (latestRevision && latestRevision.id !== activeRevision.id) {
            elements.workspaceContextBanner.textContent = `Viewing Revision ${activeIndex}. New prompts will build from here.`;
            setHidden(elements.workspaceContextBanner, false);
        } else {
            setHidden(elements.workspaceContextBanner, true);
        }

        resultRenderer.renderClarificationPanel(activeRevision, selectedClarificationSeriesId);
        resultRenderer.renderUnsupportedPanel(activeRevision);
        if (referenceRevision && activeRevision.response?.status !== "unsupported") {
            resultRenderer.renderResultPayload(referenceRevision.response, {
                hideFollowUps: activeRevision.response?.status === "needs_clarification",
            });
            setHidden(elements.emptyStatePanel, true);
        } else {
            resultRenderer.clearResultCanvas();
            setHidden(elements.emptyStatePanel, activeRevision.response?.status === "unsupported");
        }
    }

    function renderApp() {
        const hasWorkspace = workspace.revisions.length > 0;
        const hasRevisionHistory = workspace.revisions.length > 1;
        const targetSlot = hasWorkspace ? elements.workspaceComposerSlot : elements.entryComposerSlot;
        if (elements.composerCard.parentElement !== targetSlot) {
            targetSlot.appendChild(elements.composerCard);
        }

        setHidden(elements.entryView, hasWorkspace);
        setHidden(elements.workspaceView, !hasWorkspace);
        setHidden(elements.suggestionsContainer, hasWorkspace);
        elements.workspaceView.classList.toggle("is-history-collapsed", hasWorkspace && !hasRevisionHistory);
        elements.workspaceSidebar.classList.toggle("is-history-collapsed", hasWorkspace && !hasRevisionHistory);
        setHidden(elements.revisionSection, hasWorkspace && !hasRevisionHistory);
        elements.submitButton.textContent = isLoading ? "Running..." : (hasWorkspace ? "Update result" : "Ask");
        elements.queryInput.placeholder = hasWorkspace
            ? "Refine this result, compare it to something else, or replace the current subject."
            : "e.g. What is the relationship between Brent crude oil prices and inflation?";

        const activeRevision = getActiveRevision();
        if (hasWorkspace) {
            elements.workspaceTitle.textContent = workspace.title || truncateText(workspace.revisions[0].label || workspace.revisions[0].prompt, 48);
            elements.workspaceSubtitle.textContent = `${workspace.revisions.length} ${workspace.revisions.length === 1 ? "revision" : "revisions"} · Latest prompt: ${truncateText(getLatestRevision()?.prompt || "", 52)}`;
            renderRevisionList();
            renderActiveRevision();
            if (activeRevision && getLatestRevision()?.id !== activeRevision.id) {
                elements.composerContext.textContent = `Building from Revision ${getRevisionIndex(activeRevision.id) + 1}, not the latest.`;
                setHidden(elements.composerContext, false);
            } else if (activeRevision?.response?.status === "needs_clarification") {
                elements.composerContext.textContent = "Pick a series above before continuing.";
                setHidden(elements.composerContext, false);
            } else {
                elements.composerContext.textContent = "";
                setHidden(elements.composerContext, true);
            }
        } else {
            elements.composerContext.textContent = "";
            setHidden(elements.composerContext, true);
        }

        syncStatus();
    }

    function setLoading(nextLoading) {
        isLoading = nextLoading;
        elements.queryInput.disabled = nextLoading;
        elements.submitButton.disabled = nextLoading;
        elements.resetSessionButton.disabled = nextLoading;
        elements.suggestionButtons.forEach((button) => {
            button.disabled = nextLoading;
        });
        resultRenderer.getClarificationButtons().forEach((button) => {
            button.disabled = nextLoading;
        });
        resultRenderer.getFollowUpButtons().forEach((button) => {
            button.disabled = nextLoading;
        });
        renderApp();
    }

    function buildRevision(query, response, parentRevisionId) {
        return {
            id: response.revision_id,
            prompt: query,
            response,
            status: response.status,
            label: deriveRevisionLabel(response, query),
            createdAt: new Date().toISOString(),
            baseRevisionId: parentRevisionId || null,
        };
    }

    async function submitQuery({ query, requestBaseRevisionId = null, parentRevisionId = null, selectedSeriesIds = [], replaceRevisionId = null }) {
        clearError();
        setLoading(true);
        try {
            const response = await fetch("/api/ask", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    query,
                    session_id: workspace.sessionId,
                    base_revision_id: requestBaseRevisionId,
                    selected_series_id: selectedSeriesIds.find((value) => Boolean(value)) || null,
                    selected_series_ids: selectedSeriesIds,
                }),
            });
            const payload = await response.json();
            if (!response.ok) {
                throw new Error(payload?.error?.message || payload?.detail || "The query request failed.");
            }

            workspace.sessionId = payload.session_id || workspace.sessionId;
            const revision = buildRevision(query, payload, parentRevisionId);
            if (replaceRevisionId) {
                workspace.revisions = workspace.revisions.map((item) => item.id === replaceRevisionId ? revision : item);
            } else {
                workspace.revisions.push(revision);
            }
            workspace.activeRevisionId = revision.id;
            workspace.title = workspace.title || truncateText(workspace.revisions[0].label || workspace.revisions[0].prompt, 48);
            saveWorkspace();
            selectedClarificationSeriesId = null;
            if (payload.status !== "needs_clarification") {
                elements.queryInput.value = "";
            }
            renderApp();
            elements.workspaceScroll?.scrollTo({ top: 0, behavior: "smooth" });
            elements.queryInput.focus();
        } catch (error) {
            showError(error instanceof Error ? error.message : "Unexpected error.");
        } finally {
            setLoading(false);
        }
    }

    function resetWorkspace() {
        workspace = createEmptyWorkspace();
        selectedClarificationSeriesId = null;
        elements.queryInput.value = "";
        clearError();
        resultRenderer.clearClarificationPanel();
        resultRenderer.renderUnsupportedPanel(null);
        resultRenderer.clearResultCanvas();
        saveWorkspace();
        renderApp();
    }

    elements.queryForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const query = elements.queryInput.value.trim();
        if (!query) {
            showError("Enter a FRED question first.");
            return;
        }
        const activeRevision = getActiveRevision();
        await submitQuery({ query, requestBaseRevisionId: activeRevision?.id || null, parentRevisionId: activeRevision?.id || null });
    });
    elements.resetSessionButton.addEventListener("click", () => {
        resetWorkspace();
        elements.queryInput.focus();
    });
    elements.suggestionButtons.forEach((button) => {
        button.addEventListener("click", () => {
            elements.queryInput.value = button.dataset.query || "";
            elements.queryForm.requestSubmit();
        });
    });
    elements.revisionList.addEventListener("click", (event) => {
        const button = event.target.closest(".revision-item");
        if (!button) {
            return;
        }
        workspace.activeRevisionId = button.dataset.revisionId || workspace.activeRevisionId;
        selectedClarificationSeriesId = null;
        saveWorkspace();
        renderApp();
        elements.workspaceScroll?.scrollTo({ top: 0, behavior: "smooth" });
    });
    elements.clarificationOptions.addEventListener("click", async (event) => {
        const option = event.target.closest(".clarification-option");
        const activeRevision = getActiveRevision();
        if (!option || !activeRevision || activeRevision.response?.status !== "needs_clarification") {
            return;
        }
        selectedClarificationSeriesId = option.dataset.seriesId || null;
        const selectedSeriesIds = Array.isArray(activeRevision.response?.intent?.series_ids)
            ? [...activeRevision.response.intent.series_ids]
            : [];
        const targetIndex = Number.isInteger(activeRevision.response?.intent?.clarification_target_index)
            ? activeRevision.response.intent.clarification_target_index
            : 0;
        selectedSeriesIds[targetIndex] = selectedClarificationSeriesId;
        await submitQuery({
            query: activeRevision.prompt,
            requestBaseRevisionId: activeRevision.id,
            parentRevisionId: activeRevision.baseRevisionId || null,
            selectedSeriesIds,
            replaceRevisionId: activeRevision.id,
        });
    });
    elements.followUpList.addEventListener("click", (event) => {
        const button = event.target.closest(".follow-up-suggestion");
        if (!button || isLoading) {
            return;
        }
        elements.queryInput.value = button.dataset.query || "";
        elements.queryForm.requestSubmit();
    });
    elements.queryInput.addEventListener("input", () => {
        selectedClarificationSeriesId = null;
        renderApp();
    });

    renderApp();
}
