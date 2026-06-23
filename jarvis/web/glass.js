/* Glassmorphism AI dashboard */

let equityChart = null;
let allocChart = null;

async function loadPortfolio() {
  let p;
  try {
    p = await apiJson("/api/portfolio");
  } catch {
    return;
  }
  $("#equity-pill").textContent = fmtUsd(p.equity);
  const pnl = p.positions.reduce((s, x) => s + x.unrealized_pnl, 0);
  const kpis = [
    { l: "Total Equity", v: fmtUsd(p.equity) },
    { l: "Cash", v: fmtUsd(p.cash) },
    { l: "Invested", v: fmtUsd(p.equity - p.cash) },
    { l: "Unrealized P&L", v: fmtUsd(pnl), k: cls(pnl) },
    { l: "Positions", v: p.positions.length },
  ];
  $("#kpis").innerHTML = kpis
    .map((k) => `<div class="glass kpi"><div class="l">${k.l}</div><div class="v ${k.k || ""}">${k.v}</div></div>`)
    .join("");

  const labels = [...p.positions.map((x) => x.symbol), "Cash"];
  const values = [...p.positions.map((x) => x.value), p.cash];
  if (allocChart) allocChart.destroy();
  allocChart = new Chart($("#alloc-chart"), {
    type: "doughnut",
    data: { labels, datasets: [{ data: values, backgroundColor: PALETTE, borderColor: "rgba(255,255,255,.08)", borderWidth: 2 }] },
    options: {
      maintainAspectRatio: false, cutout: "64%",
      plugins: { legend: { position: "right", labels: { color: "#aab3d0", boxWidth: 12 } },
        tooltip: { callbacks: { label: (c) => ` ${c.label}: ${fmtUsd(c.parsed)}` } } },
    },
  });
}

async function loadHistory() {
  let series;
  try {
    series = await apiJson("/api/history");
  } catch {
    return;
  }
  if (equityChart) equityChart.destroy();
  equityChart = new Chart($("#equity-chart"), {
    type: "line",
    data: {
      labels: series.map((s) => s.date),
      datasets: [
        { label: "JARVIS", data: series.map((s) => s.equity_idx), borderColor: "#5cf0b0",
          backgroundColor: "rgba(92,240,176,.15)", fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2 },
        { label: "S&P 500", data: series.map((s) => s.benchmark_idx ?? null), borderColor: "#aab3d0",
          borderDash: [6, 4], fill: false, tension: 0.3, pointRadius: 0 },
      ],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#aab3d0" } } },
      scales: { x: { ticks: { color: "#aab3d0", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,.06)" } },
        y: { ticks: { color: "#aab3d0" }, grid: { color: "rgba(255,255,255,.06)" } } },
    },
  });
}

async function loadMacro() {
  let m;
  try {
    m = await apiJson("/api/macro");
  } catch {
    return;
  }
  const tiles = [];
  for (const [name, d] of Object.entries(m)) {
    if (name === "yield_curve_10y_minus_3m") {
      tiles.push(`<div class="mtile"><div class="n">Yield curve (10Y−3M)</div>
        <div class="v ${d >= 0 ? "up" : "down"}">${sign(d)}${d.toFixed(2)} pp</div>
        <div class="c ${d < 0 ? "down" : "flat"}">${d < 0 ? "inverted" : "normal"}</div></div>`);
      continue;
    }
    if (d.error) continue;
    tiles.push(`<div class="mtile"><div class="n">${name}</div>
      <div class="v">${d.last.toLocaleString()}</div>
      <div class="c ${cls(d.change_1mo_pct)}">1m ${sign(d.change_1mo_pct)}${d.change_1mo_pct}%</div></div>`);
  }
  $("#macro").innerHTML = tiles.join("") || `<span class="empty">No macro data.</span>`;
}

/* chat over SSE */
const chatBox = $("#chat");
const sendBtn = $("#chat-send");
const textInput = $("#chat-text");

function addMsg(role, text = "") {
  const d = document.createElement("div");
  d.className = `msg ${role}`;
  d.textContent = text;
  chatBox.appendChild(d);
  chatBox.scrollTop = chatBox.scrollHeight;
  return d;
}

function appendText(el, text) {
  for (const part of text.split(/(\[tool: [^\]]+\])/g)) {
    if (!part) continue;
    if (/^\[tool: [^\]]+\]$/.test(part)) {
      const s = document.createElement("span");
      s.className = "tool";
      s.textContent = `⚙ ${part.slice(1, -1)}`;
      el.appendChild(s);
    } else el.appendChild(document.createTextNode(part));
  }
  chatBox.scrollTop = chatBox.scrollHeight;
}

$("#chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = textInput.value.trim();
  if (!msg || sendBtn.disabled) return;
  textInput.value = "";
  addMsg("user", msg);
  sendBtn.disabled = true;
  const ai = addMsg("ai", "");
  try {
    const resp = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg }),
    });
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, i);
        buf = buf.slice(i + 2);
        if (!chunk.startsWith("data: ")) continue;
        const ev = JSON.parse(chunk.slice(6));
        if (ev.type === "text") appendText(ai, ev.text);
        else if (ev.type === "error") appendText(ai, `\n⚠️ ${ev.message}`);
      }
    }
  } catch (err) {
    appendText(ai, `\n⚠️ ${err.message}`);
  } finally {
    sendBtn.disabled = false;
    loadPortfolio();
  }
});

addMsg("ai", "Hi — I'm JARVIS. Ask me about the macro regime, a ticker, or your portfolio.");
loadPortfolio();
loadHistory();
loadMacro();
setInterval(loadPortfolio, 90_000);
setInterval(loadMacro, 300_000);
