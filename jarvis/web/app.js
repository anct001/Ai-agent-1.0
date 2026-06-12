/* JARVIS dashboard frontend */

const $ = (sel) => document.querySelector(sel);
const fmtUsd = (v) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const cls = (v) => (v > 0 ? "up" : v < 0 ? "down" : "flat");
const sign = (v) => (v > 0 ? "+" : "");

let equityChart = null;
let allocChart = null;
let sectorChart = null;
let btChart = null;

/* ---------- auth (Bearer token, only enforced when the server has one) ---------- */
function authHeaders() {
  const token = localStorage.getItem("jarvis_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function api(path, options = {}) {
  const resp = await fetch(path, {
    ...options,
    headers: { ...(options.headers || {}), ...authHeaders() },
  });
  if (resp.status === 401) {
    $("#token-overlay").classList.remove("hidden");
    throw new Error("unauthorized");
  }
  return resp;
}

const apiJson = (path, options) => api(path, options).then((r) => r.json());

$("#token-save").addEventListener("click", () => {
  localStorage.setItem("jarvis_token", $("#token-input").value.trim());
  $("#token-overlay").classList.add("hidden");
  boot();
});
$("#token-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("#token-save").click();
});

/* ---------- tabs ---------- */
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`#tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "journal") loadJournal();
    if (btn.dataset.tab === "trades") loadTrades();
  });
});

/* ---------- overview ---------- */
async function loadPortfolio() {
  const p = await apiJson("/api/portfolio");

  const badge = $("#mode-badge");
  badge.textContent = p.mode === "paper" ? "Paper trading" : "LIVE";
  badge.className = `badge ${p.mode}`;
  $("#equity-ticker").textContent = fmtUsd(p.equity);

  const invested = p.equity - p.cash;
  const totalPnl = p.positions.reduce((s, x) => s + x.unrealized_pnl, 0);
  const kpis = [
    { label: "Total Equity", value: fmtUsd(p.equity) },
    { label: "Cash", value: fmtUsd(p.cash), delta: `${((p.cash / p.equity) * 100).toFixed(1)}% of equity` },
    { label: "Invested", value: fmtUsd(invested), delta: `${p.positions.length} position${p.positions.length === 1 ? "" : "s"}` },
    { label: "Unrealized P&L", value: fmtUsd(totalPnl), valueClass: cls(totalPnl) },
    { label: "Trades Today", value: `${p.trades_today} / ${p.risk_limits.max_orders_per_day}` },
  ];
  $("#kpi-row").innerHTML = kpis
    .map(
      (k) => `<div class="kpi">
        <div class="label">${k.label}</div>
        <div class="value ${k.valueClass || ""}">${k.value}</div>
        ${k.delta ? `<div class="delta flat">${k.delta}</div>` : ""}
      </div>`
    )
    .join("");

  renderPositions(p.positions);
  renderAllocation(p);
  renderSectors(p.sector_allocation || {});
  renderRisk(p.risk_limits);
}

function renderSectors(sectors) {
  const entries = Object.entries(sectors);
  const empty = $("#sector-empty");
  const ctx = $("#sector-chart");
  if (sectorChart) sectorChart.destroy();
  if (!entries.length) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");
  sectorChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: entries.map(([k]) => k),
      datasets: [{ data: entries.map(([, v]) => v), backgroundColor: PALETTE, borderColor: "#141923", borderWidth: 2 }],
    },
    options: {
      maintainAspectRatio: false,
      cutout: "62%",
      plugins: {
        legend: { position: "right", labels: { color: "#8b97ab", boxWidth: 12 } },
        tooltip: { callbacks: { label: (c) => ` ${c.label}: ${fmtUsd(c.parsed)}` } },
      },
    },
  });
}

async function loadAlerts() {
  let alerts;
  try {
    alerts = await apiJson("/api/alerts");
  } catch {
    return;
  }
  const banner = $("#alerts-banner");
  if (alerts.length) {
    const critical = alerts.some((a) => a.severity === "critical");
    banner.className = `alerts-banner ${critical ? "critical" : ""}`;
    banner.innerHTML = alerts.map((a) => `⚠ <strong>${a.title}</strong> — ${a.detail}`).join("<br/>");
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
  $("#alerts-list").innerHTML = alerts.length
    ? alerts
        .map(
          (a) => `<div class="alert-item ${a.severity}">
            <div class="t">${a.title}</div>
            <div class="d">${a.detail}</div>
          </div>`
        )
        .join("")
    : `<span class="empty">No alerts today — thresholds are configurable in .env.</span>`;
}

function renderPositions(positions) {
  const table = $("#positions-table");
  if (!positions.length) {
    table.innerHTML = `<tr><td class="empty">No open positions — ask the agent to find an opportunity.</td></tr>`;
    return;
  }
  const rows = positions
    .map(
      (x) => `<tr>
        <td><strong>${x.symbol}</strong></td>
        <td>${x.qty}</td>
        <td>${fmtUsd(x.avg_cost)}</td>
        <td>${fmtUsd(x.price)}</td>
        <td>${fmtUsd(x.value)}</td>
        <td class="${cls(x.unrealized_pnl)}">${sign(x.unrealized_pnl)}${fmtUsd(x.unrealized_pnl)}</td>
        <td class="${cls(x.unrealized_pnl_pct)}">${sign(x.unrealized_pnl_pct)}${x.unrealized_pnl_pct.toFixed(2)}%</td>
      </tr>`
    )
    .join("");
  table.innerHTML =
    `<tr><th>Symbol</th><th>Qty</th><th>Avg Cost</th><th>Price</th><th>Value</th><th>P&L</th><th>P&L %</th></tr>` + rows;
}

const PALETTE = ["#5aa9ff", "#3ecf8e", "#ffc16b", "#b78bff", "#ff8fab", "#6be3ff", "#ffd76b", "#9dff8b", "#ff9b6b", "#8b97ab"];

function renderAllocation(p) {
  const labels = [...p.positions.map((x) => x.symbol), "Cash"];
  const values = [...p.positions.map((x) => x.value), p.cash];
  const ctx = $("#alloc-chart");
  if (allocChart) allocChart.destroy();
  allocChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{ data: values, backgroundColor: PALETTE, borderColor: "#141923", borderWidth: 2 }],
    },
    options: {
      maintainAspectRatio: false,
      cutout: "62%",
      plugins: {
        legend: { position: "right", labels: { color: "#8b97ab", boxWidth: 12 } },
        tooltip: {
          callbacks: {
            label: (c) => ` ${c.label}: ${fmtUsd(c.parsed)} (${((c.parsed / values.reduce((a, b) => a + b, 0)) * 100).toFixed(1)}%)`,
          },
        },
      },
    },
  });
}

function renderRisk(limits) {
  const items = [
    { label: "Max single order", value: `${(limits.max_order_pct_of_equity * 100).toFixed(0)}%` },
    { label: "Max position size", value: `${(limits.max_position_pct_of_equity * 100).toFixed(0)}%` },
    { label: "Cash reserve floor", value: `${(limits.min_cash_reserve_pct * 100).toFixed(0)}%` },
    { label: "Max orders / day", value: limits.max_orders_per_day },
  ];
  $("#risk-grid").innerHTML = items
    .map((i) => `<div class="risk-item"><div class="label">${i.label}</div><div class="value">${i.value}</div></div>`)
    .join("");
}

async function loadHistory() {
  const series = await apiJson("/api/history");
  const empty = $("#equity-empty");
  if (series.length < 2) {
    empty.classList.remove("hidden");
  } else {
    empty.classList.add("hidden");
  }
  const ctx = $("#equity-chart");
  if (equityChart) equityChart.destroy();
  equityChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: series.map((s) => s.date),
      datasets: [
        {
          label: "JARVIS",
          data: series.map((s) => s.equity_idx),
          borderColor: "#5aa9ff",
          backgroundColor: "rgba(90,169,255,.12)",
          fill: true,
          tension: 0.25,
          pointRadius: series.length > 30 ? 0 : 3,
        },
        {
          label: "S&P 500",
          data: series.map((s) => s.benchmark_idx ?? null),
          borderColor: "#8b97ab",
          borderDash: [6, 4],
          fill: false,
          tension: 0.25,
          pointRadius: 0,
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: "#8b97ab" } } },
      scales: {
        x: { ticks: { color: "#8b97ab", maxTicksLimit: 8 }, grid: { color: "#1b2230" } },
        y: { ticks: { color: "#8b97ab" }, grid: { color: "#1b2230" } },
      },
    },
  });
}

async function loadMacro() {
  const macro = await apiJson("/api/macro");
  const tiles = [];
  for (const [name, d] of Object.entries(macro)) {
    if (name === "yield_curve_10y_minus_3m") {
      tiles.push(`<div class="macro-tile signal">
        <div class="name">Yield curve (10Y − 3M)</div>
        <div class="last ${d >= 0 ? "up" : "down"}">${sign(d)}${d.toFixed(2)} pp</div>
        <div class="changes flat">${d < 0 ? "inverted — recession signal" : "positive slope"}</div>
      </div>`);
      continue;
    }
    if (d.error) continue;
    tiles.push(`<div class="macro-tile">
      <div class="name">${name}</div>
      <div class="last">${d.last.toLocaleString()}</div>
      <div class="changes">
        <span class="${cls(d.change_1d_pct)}">1d ${sign(d.change_1d_pct)}${d.change_1d_pct}%</span>
        <span class="${cls(d.change_1mo_pct)}">1m ${sign(d.change_1mo_pct)}${d.change_1mo_pct}%</span>
        <span class="${cls(d.change_6mo_pct)}">6m ${sign(d.change_6mo_pct)}${d.change_6mo_pct}%</span>
      </div>
    </div>`);
  }
  $("#macro-grid").innerHTML = tiles.join("") || `<span class="empty">No macro data available.</span>`;
}

/* ---------- journal ---------- */
async function loadJournal() {
  const j = await apiJson("/api/journal");
  $("#theses-list").innerHTML = j.theses.length
    ? j.theses
        .map(
          (t) => `<div class="thesis-card">
            <div class="head">
              <span class="sym">${t.symbol}</span>
              <span class="conviction ${t.conviction}">${t.conviction}</span>
            </div>
            <div class="body">${t.thesis}</div>
            <div class="meta">Horizon: ${t.horizon} · Invalidation: ${t.invalidation}<br/>${t.timestamp.slice(0, 10)}</div>
          </div>`
        )
        .join("")
    : `<span class="empty">No theses yet — run an analysis and the agent will record its views here.</span>`;

  $("#lessons-list").innerHTML = j.lessons.length
    ? j.lessons
        .map(
          (l) => `<div class="thesis-card">
            <div class="body">${l.lesson}</div>
            <div class="meta">${l.context ? l.context + "<br/>" : ""}${l.timestamp.slice(0, 10)}</div>
          </div>`
        )
        .join("")
    : `<span class="empty">No lessons recorded yet.</span>`;
}

/* ---------- trades ---------- */
async function loadTrades() {
  const trades = await apiJson("/api/trades");
  const table = $("#trades-table");
  if (!trades.length) {
    table.innerHTML = `<tr><td class="empty">No trades yet.</td></tr>`;
    return;
  }
  table.innerHTML =
    `<tr><th>Time (UTC)</th><th>Side</th><th>Symbol</th><th>Qty</th><th>Price</th><th>Value</th><th>Rationale</th></tr>` +
    trades
      .map(
        (t) => `<tr>
          <td>${t.timestamp.slice(0, 16).replace("T", " ")}</td>
          <td class="${t.side === "buy" ? "up" : "down"}">${t.side.toUpperCase()}</td>
          <td><strong>${t.symbol}</strong></td>
          <td>${t.qty}</td>
          <td>${fmtUsd(t.price)}</td>
          <td>${fmtUsd(t.value)}</td>
          <td class="rationale">${t.rationale || ""}</td>
        </tr>`
      )
      .join("");
}

/* ---------- chat (SSE over fetch) ---------- */
const chatForm = $("#chat-form");
const chatText = $("#chat-text");
const chatSend = $("#chat-send");
const chatMessages = $("#chat-messages");

function addMsg(role, text = "") {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

function appendAgentText(el, text) {
  // Render "[tool: name]" markers as styled notes instead of raw text.
  const parts = text.split(/(\[tool: [^\]]+\])/g);
  for (const part of parts) {
    if (!part) continue;
    if (/^\[tool: [^\]]+\]$/.test(part)) {
      const note = document.createElement("span");
      note.className = "tool-note";
      note.textContent = `⚙ ${part.slice(1, -1)}`;
      el.appendChild(note);
    } else {
      el.appendChild(document.createTextNode(part));
    }
  }
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function showApproval(req) {
  const o = req.order;
  $("#approval-body").innerHTML = `
    <div class="row"><span class="k">Action</span><span class="${o.side === "buy" ? "up" : "down"}">${o.side.toUpperCase()} ${o.qty} ${o.symbol}</span></div>
    <div class="row"><span class="k">Est. price</span><span>${fmtUsd(o.est_price)}</span></div>
    <div class="row"><span class="k">Est. value</span><span>${fmtUsd(o.est_value)}</span></div>
    <div class="row"><span class="k">Conviction</span><span>${o.conviction}</span></div>
    <div class="rationale-text">${o.rationale}</div>`;
  $("#approval-overlay").classList.remove("hidden");

  const decide = (approve) => {
    $("#approval-overlay").classList.add("hidden");
    api(`/api/approval/${req.id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approve }),
    });
  };
  $("#approve-yes").onclick = () => decide(true);
  $("#approve-no").onclick = () => decide(false);
}

async function sendChat(message) {
  addMsg("user", message);
  chatSend.disabled = true;
  const agentEl = addMsg("agent", "");

  try {
    const resp = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const chunk = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        if (!chunk.startsWith("data: ")) continue;
        const event = JSON.parse(chunk.slice(6));
        if (event.type === "text") appendAgentText(agentEl, event.text);
        else if (event.type === "approval_request") showApproval(event);
        else if (event.type === "error") addMsg("error", event.message);
      }
    }
  } catch (err) {
    addMsg("error", `Connection error: ${err.message}`);
  } finally {
    chatSend.disabled = false;
    loadPortfolio();
    loadHistory();
  }
}

chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const message = chatText.value.trim();
  if (!message || chatSend.disabled) return;
  chatText.value = "";
  sendChat(message);
});

document.querySelectorAll(".chip").forEach((chip) =>
  chip.addEventListener("click", () => {
    if (!chatSend.disabled) sendChat(chip.dataset.prompt);
  })
);

/* ---------- chat persistence ---------- */
async function loadChatHistory() {
  let transcript;
  try {
    transcript = await apiJson("/api/chat/history");
  } catch {
    return;
  }
  if (!transcript.length) return;
  chatMessages.innerHTML = "";
  for (const msg of transcript) {
    if (msg.role === "user") addMsg("user", msg.text);
    else appendAgentText(addMsg("agent", ""), msg.text);
  }
}

$("#chat-reset").addEventListener("click", async () => {
  if (!confirm("Start a new conversation? The journal and portfolio are kept.")) return;
  await api("/api/chat/reset", { method: "POST" });
  chatMessages.innerHTML = "";
  addMsg("agent", "Fresh start. The portfolio, journal, and trade history are all intact — what's next?");
});

/* ---------- backtest ---------- */
function parseWeights(text) {
  const weights = {};
  for (const part of text.split(",")) {
    const [sym, w] = part.split("=").map((s) => s.trim());
    if (!sym || !w || isNaN(parseFloat(w))) throw new Error(`Cannot parse "${part.trim()}" — use SYM=0.4`);
    weights[sym.toUpperCase()] = parseFloat(w);
  }
  return weights;
}

$("#backtest-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = $("#bt-status");
  const runBtn = $("#bt-run");
  let weights;
  try {
    weights = parseWeights($("#bt-weights").value);
  } catch (err) {
    status.textContent = err.message;
    status.classList.remove("hidden");
    return;
  }
  runBtn.disabled = true;
  status.textContent = "Downloading history and simulating…";
  status.classList.remove("hidden");
  try {
    const resp = await api("/api/backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        weights,
        period: $("#bt-period").value,
        rebalance: $("#bt-rebalance").value,
        benchmark: $("#bt-benchmark").value.trim().toUpperCase() || "SPY",
      }),
    });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || resp.statusText);
    }
    renderBacktest(await resp.json());
    status.classList.add("hidden");
  } catch (err) {
    status.textContent = `Backtest failed: ${err.message}`;
  } finally {
    runBtn.disabled = false;
  }
});

function renderBacktest(r) {
  $("#bt-results").classList.remove("hidden");
  const p = r.portfolio;
  const b = r.benchmark || {};
  const metric = (label, val, benchVal, suffix = "%") => ({
    label,
    value: `${val}${suffix}`,
    delta: benchVal !== undefined ? `${r.benchmark_symbol}: ${benchVal}${suffix}` : "",
    valueClass: label.includes("drawdown") ? "down" : cls(val),
  });
  const kpis = [
    metric("Total return", p.total_return_pct, b.total_return_pct),
    metric("CAGR", p.cagr_pct, b.cagr_pct),
    metric("Volatility", p.annualized_volatility_pct, b.annualized_volatility_pct),
    metric("Sharpe", p.sharpe_ratio, b.sharpe_ratio, ""),
    metric("Max drawdown", p.max_drawdown_pct, b.max_drawdown_pct),
  ];
  if (r.excess_cagr_pct !== undefined) {
    kpis.push({
      label: "Excess CAGR",
      value: `${sign(r.excess_cagr_pct)}${r.excess_cagr_pct} pp`,
      delta: "vs benchmark",
      valueClass: cls(r.excess_cagr_pct),
    });
  }
  $("#bt-metrics").innerHTML = kpis
    .map(
      (k) => `<div class="kpi">
        <div class="label">${k.label}</div>
        <div class="value ${k.valueClass || ""}">${k.value}</div>
        ${k.delta ? `<div class="delta flat">${k.delta}</div>` : ""}
      </div>`
    )
    .join("");

  const ctx = $("#bt-chart");
  if (btChart) btChart.destroy();
  btChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: r.curve.map((s) => s.date),
      datasets: [
        {
          label: "Strategy",
          data: r.curve.map((s) => s.portfolio_idx),
          borderColor: "#3ecf8e",
          backgroundColor: "rgba(62,207,142,.12)",
          fill: true,
          tension: 0.25,
          pointRadius: 0,
        },
        {
          label: r.benchmark_symbol || "Benchmark",
          data: r.curve.map((s) => s.benchmark_idx ?? null),
          borderColor: "#8b97ab",
          borderDash: [6, 4],
          fill: false,
          tension: 0.25,
          pointRadius: 0,
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: "#8b97ab" } } },
      scales: {
        x: { ticks: { color: "#8b97ab", maxTicksLimit: 10 }, grid: { color: "#1b2230" } },
        y: { ticks: { color: "#8b97ab" }, grid: { color: "#1b2230" } },
      },
    },
  });
}

/* ---------- boot ---------- */
async function boot() {
  try {
    await loadPortfolio();
  } catch (err) {
    if (err.message === "unauthorized") return; // token modal is up
    throw err;
  }
  loadHistory();
  loadMacro();
  loadAlerts();
  loadChatHistory();
}

boot();
setInterval(() => loadPortfolio().catch(() => {}), 90_000);
setInterval(loadMacro, 300_000);
setInterval(loadAlerts, 120_000);
