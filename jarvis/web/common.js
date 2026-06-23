/* Shared helpers for the Quant and Glass dashboards. */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const fmtUsd = (v) =>
  (v ?? 0).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
const fmtPct = (v) => `${v > 0 ? "+" : ""}${(v ?? 0).toFixed(2)}%`;
const cls = (v) => (v > 0 ? "up" : v < 0 ? "down" : "flat");
const sign = (v) => (v > 0 ? "+" : "");

function authHeaders() {
  const t = localStorage.getItem("jarvis_token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function api(path, opts = {}) {
  const r = await fetch(path, {
    ...opts,
    headers: { ...(opts.headers || {}), ...authHeaders() },
  });
  if (r.status === 401) {
    const t = prompt("Dashboard token required:");
    if (t) {
      localStorage.setItem("jarvis_token", t);
      return api(path, opts);
    }
  }
  return r;
}

const apiJson = (path, opts) => api(path, opts).then((r) => r.json());

/* Color a value from red (negative) to green (positive), |v|<=1 → strongest. */
function corrColor(v) {
  const t = Math.max(-1, Math.min(1, v));
  if (t >= 0) {
    const a = 0.12 + t * 0.55;
    return `rgba(62, 207, 142, ${a.toFixed(3)})`;
  }
  const a = 0.12 + -t * 0.55;
  return `rgba(255, 107, 107, ${a.toFixed(3)})`;
}

/* Shared dark Chart.js theme bits. */
const GRID = "#1b2230";
const MUTED = "#8b97ab";
const PALETTE = [
  "#5aa9ff", "#3ecf8e", "#ffc16b", "#b78bff", "#ff8fab",
  "#6be3ff", "#ffd76b", "#9dff8b", "#ff9b6b", "#8b97ab",
];
