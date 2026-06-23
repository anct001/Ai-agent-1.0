/* Quant Research dashboard */

function metric(label, value, klass = "flat", suffix = "") {
  return `<div class="metric"><div class="l">${label}</div>
    <div class="v ${klass}">${value}${suffix}</div></div>`;
}

async function loadQuant() {
  let q;
  try {
    q = await apiJson("/api/quant");
  } catch {
    return;
  }
  $("#asof").textContent = new Date().toISOString().slice(0, 16).replace("T", " ") + " UTC";

  const r = q.risk || {};
  const c = q.concentration || {};
  const cells = [];
  cells.push(metric("Equity", fmtUsd(q.equity)));
  if (!r.insufficient_data) {
    cells.push(metric("Ann. Return", r.annualized_return_pct, cls(r.annualized_return_pct), "%"));
    cells.push(metric("Ann. Vol", r.annualized_volatility_pct, "flat", "%"));
    cells.push(metric("Sharpe", r.sharpe_ratio, cls(r.sharpe_ratio)));
    cells.push(metric("Sortino", r.sortino_ratio, cls(r.sortino_ratio)));
    cells.push(metric("Max DD", r.max_drawdown_pct, "down", "%"));
    cells.push(metric("VaR 95%", r.daily_var_95_pct, "down", "%"));
    cells.push(metric("CVaR 95%", r.daily_cvar_95_pct, "down", "%"));
  } else {
    cells.push(metric("Risk stats", "need history", "muted"));
  }
  cells.push(metric("Eff. N", c.effective_n ?? 0));
  $("#metrics").innerHTML = cells.join("");

  // concentration panel
  $("#concentration").innerHTML = `
    <div class="r"><span class="k">Holdings</span><span>${c.holdings ?? 0}</span></div>
    <div class="r"><span class="k">Herfindahl (HHI)</span><span>${c.hhi ?? 0}</span></div>
    <div class="r"><span class="k">Effective positions</span><span>${c.effective_n ?? 0}</span></div>
    <div class="r"><span class="k">Top weight</span><span>${(c.top_weight_pct ?? 0).toFixed(1)}%</span></div>`;

  renderCorrelation(q.correlation || { symbols: [], matrix: [] });
  renderBars("#exp-sector", q.sector_allocation);
  renderBars("#exp-country", q.country_allocation);
  renderBars("#exp-asset", q.asset_class_allocation);
  renderHoldings(q.positions || []);
}

function renderCorrelation(corr) {
  const note = $("#corr-note");
  const el = $("#corr");
  if (corr.error) {
    el.innerHTML = `<span class="muted">${corr.error}</span>`;
    return;
  }
  if (!corr.symbols.length || !corr.matrix.length) {
    el.innerHTML = `<span class="muted">Need ≥2 holdings for a correlation matrix.</span>`;
    return;
  }
  note.textContent = `· ${corr.symbols.length}×${corr.symbols.length}`;
  let html = '<table class="corr"><tr><th></th>';
  for (const s of corr.symbols) html += `<th>${s}</th>`;
  html += "</tr>";
  corr.matrix.forEach((row, i) => {
    html += `<tr><td class="sym">${corr.symbols[i]}</td>`;
    row.forEach((v) => {
      html += `<td style="background:${corrColor(v)}">${v.toFixed(2)}</td>`;
    });
    html += "</tr>";
  });
  html += "</table>";
  el.innerHTML = html;
}

function renderBars(sel, data) {
  const wrap = $(sel + " .bars");
  const entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, v]) => s + v, 0) || 1;
  if (!entries.length) {
    wrap.innerHTML = `<span class="muted">No positions.</span>`;
    return;
  }
  wrap.innerHTML = entries
    .map(([k, v]) => {
      const pct = (v / total) * 100;
      return `<div class="bar-row">
        <div class="top"><span>${k}</span><span class="pct">${pct.toFixed(1)}%</span></div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
      </div>`;
    })
    .join("");
}

function renderHoldings(positions) {
  const t = $("#holdings");
  if (!positions.length) {
    t.innerHTML = `<tr><td class="muted">No open positions.</td></tr>`;
    return;
  }
  t.innerHTML =
    `<tr><th>Symbol</th><th>Qty</th><th>Avg Cost</th><th>Price</th><th>Value</th><th>P&L</th><th>P&L %</th></tr>` +
    positions
      .map(
        (p) => `<tr>
        <td>${p.symbol}</td><td>${p.qty}</td><td>${fmtUsd(p.avg_cost)}</td>
        <td>${fmtUsd(p.price)}</td><td>${fmtUsd(p.value)}</td>
        <td class="${cls(p.unrealized_pnl)}">${fmtUsd(p.unrealized_pnl)}</td>
        <td class="${cls(p.unrealized_pnl_pct)}">${fmtPct(p.unrealized_pnl_pct)}</td>
      </tr>`
      )
      .join("");
}

async function loadCurves() {
  let series;
  try {
    series = await apiJson("/api/history");
  } catch {
    return;
  }
  if (series.length < 2) return;
  const equity = series.map((s) => s.equity);

  // Underwater drawdown
  let peak = equity[0];
  const dd = equity.map((e) => {
    peak = Math.max(peak, e);
    return ((e / peak - 1) * 100).toFixed(2);
  });
  new Chart($("#dd-chart"), {
    type: "line",
    data: {
      labels: series.map((s) => s.date),
      datasets: [{ data: dd, borderColor: "#ff6b6b", backgroundColor: "rgba(255,107,107,.15)", fill: true, tension: 0.2, pointRadius: 0 }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: { ticks: { color: MUTED, maxTicksLimit: 8 }, grid: { color: GRID } }, y: { ticks: { color: MUTED }, grid: { color: GRID } } },
    },
  });

  // Daily return histogram
  const rets = [];
  for (let i = 1; i < equity.length; i++) rets.push((equity[i] / equity[i - 1] - 1) * 100);
  const bins = 15;
  const lo = Math.min(...rets), hi = Math.max(...rets);
  const width = (hi - lo) / bins || 1;
  const counts = new Array(bins).fill(0);
  rets.forEach((x) => {
    const idx = Math.min(bins - 1, Math.floor((x - lo) / width));
    counts[idx]++;
  });
  new Chart($("#dist-chart"), {
    type: "bar",
    data: {
      labels: counts.map((_, i) => (lo + width * (i + 0.5)).toFixed(1) + "%"),
      datasets: [{ data: counts, backgroundColor: "#46e0b0" }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: { ticks: { color: MUTED, maxTicksLimit: 8 }, grid: { display: false } }, y: { ticks: { color: MUTED }, grid: { color: GRID } } },
    },
  });
}

loadQuant();
loadCurves();
setInterval(loadQuant, 120_000);
