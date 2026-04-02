import { mountWorkspaceApp } from "./workspace-app.js";

const THEME_KEY = "fred-query-theme";

function initTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    const theme = saved || (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    document.documentElement.dataset.theme = theme;
}

function toggleTheme() {
    const current = document.documentElement.dataset.theme || "dark";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem(THEME_KEY, next);
    window.dispatchEvent(new Event("themechange"));
}

initTheme();
document.getElementById("theme-toggle")?.addEventListener("click", toggleTheme);

mountWorkspaceApp();
