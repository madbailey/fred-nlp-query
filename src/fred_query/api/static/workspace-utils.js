export const STATUS_LABELS = {
    completed: "Completed",
    working: "Working",
    needs_clarification: "Clarify",
    unsupported: "Unsupported",
    failed: "Failed",
};

export const FREQUENCY_LABELS = {
    D: "Daily",
    W: "Weekly",
    BW: "Biweekly",
    M: "Monthly",
    Q: "Quarterly",
    SA: "Semiannual",
    A: "Annual",
};

export function humanize(value) {
    if (!value) {
        return "";
    }

    return String(value)
        .replace(/_/g, " ")
        .replace(/\b\w/g, (match) => match.toUpperCase());
}

export function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

export function truncateText(text, maxLength = 72) {
    if (!text) {
        return "";
    }

    if (text.length <= maxLength) {
        return text;
    }

    return `${text.slice(0, maxLength).trimEnd()}\u2026`;
}

export function formatDate(value) {
    if (!value) {
        return "N/A";
    }

    return new Intl.DateTimeFormat("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
    }).format(new Date(`${value}T00:00:00`));
}

export function formatValue(value) {
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

export function formatPercent(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "N/A";
    }

    return `${formatValue(value)}%`;
}

export function formatFrequencyLabel(value) {
    const normalized = (value || "").toUpperCase();
    return FREQUENCY_LABELS[normalized] || value || "";
}

export function formatRevisionStatus(status) {
    return STATUS_LABELS[status] || humanize(status);
}
