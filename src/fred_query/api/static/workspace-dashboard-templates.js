import { escapeHtml } from "./workspace-utils.js";

function renderWarnings(warnings) {
    if (!warnings?.length) {
        return "";
    }

    return `
        <div class="dashboard-warning-list">
            ${warnings.map((warning) => `<span class="warning-chip">${escapeHtml(warning)}</span>`).join("")}
        </div>
    `;
}

function renderActions(actions) {
    if (!actions?.length) {
        return "";
    }

    return `
        <section class="dashboard-actions" aria-label="Next actions">
            <p class="dashboard-section-label">Next actions</p>
            <div class="dashboard-action-grid">
                ${actions.map((action) => `
                    <button
                        type="button"
                        class="follow-up-suggestion dashboard-action-button"
                        data-query="${escapeHtml(action.query)}"
                        title="${escapeHtml(action.title || action.label)}"
                    >
                        ${escapeHtml(action.label)}
                    </button>
                `).join("")}
            </div>
        </section>
    `;
}

function renderDetails(details) {
    if (!details?.length) {
        return "";
    }

    return `
        <details class="dashboard-details">
            <summary class="dashboard-details-toggle">Data details</summary>
            <dl class="dashboard-details-grid">
                ${details.map((item) => `
                    <div class="dashboard-detail-row">
                        <dt>${escapeHtml(item.label)}</dt>
                        <dd>
                            ${item.href
                                ? `<a class="dashboard-detail-link" href="${escapeHtml(item.href)}" target="_blank" rel="noreferrer">${escapeHtml(item.value)}</a>`
                                : escapeHtml(item.value)
                            }
                        </dd>
                    </div>
                `).join("")}
            </dl>
        </details>
    `;
}

function renderSummary(summary, { headline = null } = {}) {
    if (!summary) {
        return "";
    }

    return `
        <div class="dashboard-hero-main">
            <p class="dashboard-section-label">Snapshot</p>
            ${headline || ""}
            <p class="dashboard-latest-label">${escapeHtml(summary.label)}</p>
            <p class="dashboard-latest-value">${escapeHtml(summary.value)}</p>
            <p class="dashboard-latest-note">${escapeHtml(summary.note)}</p>
        </div>
    `;
}

function renderHeroStats(heroStats) {
    if (!heroStats?.length) {
        return "";
    }

    return `
        <div class="dashboard-stat-strip">
            ${heroStats.map((stat) => `
                <article class="dashboard-stat-card">
                    <p class="dashboard-stat-label">${escapeHtml(stat.label)}</p>
                    <p class="dashboard-stat-value">${escapeHtml(stat.value)}</p>
                    <p class="dashboard-stat-note">${escapeHtml(stat.note)}</p>
                </article>
            `).join("")}
        </div>
    `;
}

function renderInsight(insight) {
    if (!insight) {
        return "";
    }

    return `
        <section class="dashboard-insight">
            <p class="dashboard-section-label">What matters</p>
            <p class="dashboard-insight-lead">${escapeHtml(insight.lead)}</p>
            <div class="dashboard-insight-support">
                ${insight.support.map((line) => `<p>${escapeHtml(line)}</p>`).join("")}
            </div>
        </section>
    `;
}

function renderPairCards(cards) {
    if (!cards?.length) {
        return "";
    }

    return `
        <section class="dashboard-pair-grid" aria-label="Series snapshot">
            ${cards.map((card) => `
                <article class="dashboard-pair-card">
                    <div class="dashboard-pair-header">
                        <p class="dashboard-pair-label">${escapeHtml(card.label)}</p>
                        <p class="dashboard-pair-title">${escapeHtml(card.title)}</p>
                    </div>
                    <p class="dashboard-pair-value">${escapeHtml(card.value)}</p>
                    <p class="dashboard-pair-note">${escapeHtml(card.note)}</p>
                    ${card.meta?.length
                        ? `
                            <div class="dashboard-pair-meta">
                                ${card.meta.map((item) => `<span class="badge">${escapeHtml(item)}</span>`).join("")}
                            </div>
                        `
                        : ""
                    }
                </article>
            `).join("")}
        </section>
    `;
}

function renderRankings(rankings) {
    if (!rankings?.length) {
        return "";
    }

    return `
        <section class="dashboard-ranking-panel" aria-label="Top ranks">
            <p class="dashboard-section-label">Top ranks</p>
            <div class="dashboard-ranking-list">
                ${rankings.map((item) => `
                    <article class="dashboard-ranking-row">
                        <p class="dashboard-ranking-rank">${escapeHtml(item.rank)}</p>
                        <div class="dashboard-ranking-copy">
                            <p class="dashboard-ranking-label">${escapeHtml(item.label)}</p>
                            <p class="dashboard-ranking-subtitle">${escapeHtml(item.subtitle)}</p>
                        </div>
                        <div class="dashboard-ranking-value-group">
                            <p class="dashboard-ranking-value">${escapeHtml(item.value)}</p>
                            <p class="dashboard-ranking-note">${escapeHtml(item.note)}</p>
                        </div>
                    </article>
                `).join("")}
            </div>
        </section>
    `;
}

function renderSingleSeriesDashboard(model) {
    return `
        <div class="dashboard-shell dashboard-shell-single-series">
            <section class="dashboard-hero">
                ${renderSummary(model.latest, {
                    headline: `
                        <div class="dashboard-badge-row">
                            ${model.badges.map((badge) => `<span class="badge">${escapeHtml(badge)}</span>`).join("")}
                        </div>
                    `,
                })}
                ${renderHeroStats(model.heroStats)}
            </section>

            ${renderInsight(model.insight)}
            ${renderWarnings(model.warnings)}
            ${renderActions(model.actions)}
            ${renderDetails(model.details)}
        </div>
    `;
}

function renderPairedSeriesDashboard(model) {
    return `
        <div class="dashboard-shell">
            <section class="dashboard-hero">
                ${renderSummary(model.summary, {
                    headline: `
                        <div class="dashboard-badge-row">
                            ${model.badges.map((badge) => `<span class="badge">${escapeHtml(badge)}</span>`).join("")}
                        </div>
                        <p class="dashboard-headline">${escapeHtml(model.title)}</p>
                    `,
                })}
                ${renderHeroStats(model.heroStats)}
            </section>

            ${renderPairCards(model.pairCards)}
            ${renderInsight(model.insight)}
            ${renderWarnings(model.warnings)}
            ${renderActions(model.actions)}
            ${renderDetails(model.details)}
        </div>
    `;
}

function renderCrossSectionDashboard(model) {
    return `
        <div class="dashboard-shell dashboard-shell-cross-section">
            <section class="dashboard-hero">
                ${renderSummary(model.summary, {
                    headline: `
                        <div class="dashboard-badge-row">
                            ${model.badges.map((badge) => `<span class="badge">${escapeHtml(badge)}</span>`).join("")}
                        </div>
                        <p class="dashboard-headline">${escapeHtml(model.title)}</p>
                    `,
                })}
                ${renderHeroStats(model.heroStats)}
            </section>

            ${renderRankings(model.rankings)}
            ${renderInsight(model.insight)}
            ${renderWarnings(model.warnings)}
            ${renderActions(model.actions)}
            ${renderDetails(model.details)}
        </div>
    `;
}

export function renderDashboardMarkup(model) {
    if (!model) {
        return "";
    }

    if (model.mode === "single_series") {
        return renderSingleSeriesDashboard(model);
    }

    if (model.mode === "comparison") {
        return renderPairedSeriesDashboard(model);
    }

    if (model.mode === "pair_analysis") {
        return renderPairedSeriesDashboard(model);
    }

    if (model.mode === "cross_section") {
        return renderCrossSectionDashboard(model);
    }

    return "";
}
