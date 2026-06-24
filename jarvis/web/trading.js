/* JARVIS Trading Terminal — trading.js */

/* ─── PARTICLE BACKGROUND ─── */
(function () {
  const canvas = document.getElementById('particles-canvas');
  const ctx = canvas.getContext('2d');
  let W, H, particles = [];

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }

  function initParticles(n = 70) {
    particles = Array.from({ length: n }, () => ({
      x: Math.random() * W,
      y: Math.random() * H,
      r: Math.random() * 1.4 + 0.3,
      vx: (Math.random() - 0.5) * 0.25,
      vy: (Math.random() - 0.5) * 0.25,
      alpha: Math.random() * 0.5 + 0.2,
    }));
  }

  function drawParticles() {
    ctx.clearRect(0, 0, W, H);
    const isDark = document.documentElement.dataset.theme !== 'light';
    const color = isDark ? '150,180,255' : '60,100,200';

    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${color},${p.alpha})`;
      ctx.fill();

      // Connect close particles
      for (let j = i + 1; j < particles.length; j++) {
        const q = particles[j];
        const dx = p.x - q.x, dy = p.y - q.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 100) {
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(q.x, q.y);
          ctx.strokeStyle = `rgba(${color},${(1 - dist / 100) * 0.12})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }

      p.x += p.vx; p.y += p.vy;
      if (p.x < 0) p.x = W;
      if (p.x > W) p.x = 0;
      if (p.y < 0) p.y = H;
      if (p.y > H) p.y = 0;
    }
    requestAnimationFrame(drawParticles);
  }

  resize();
  initParticles();
  drawParticles();
  window.addEventListener('resize', () => { resize(); initParticles(); });
})();

/* ─── CLOCK ─── */
function updateClock() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const t = `${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}:${pad(now.getUTCSeconds())}`;
  const el = document.getElementById('clock-time');
  if (el) el.textContent = t;
  const sb = document.getElementById('sb-time');
  if (sb) sb.textContent = t + ' UTC';
}
setInterval(updateClock, 1000);
updateClock();

/* ─── SIDEBAR NAVIGATION ─── */
const sections = {};
document.querySelectorAll('.section').forEach(s => { sections[s.id.replace('section-', '')] = s; });

function switchSection(name) {
  document.querySelectorAll('.menu-item').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));

  const item = document.querySelector(`[data-section="${name}"]`);
  if (item) item.classList.add('active');
  const sec = document.getElementById(`section-${name}`);
  if (sec) { sec.classList.add('active'); onSectionActivated(name); }
}

document.querySelectorAll('.menu-item[data-section]').forEach(el => {
  el.addEventListener('click', () => switchSection(el.dataset.section));
});

function onSectionActivated(name) {
  if (name === 'agents')    renderAgents();
  if (name === 'markets')   { renderHeatmap(); loadMarketMeta(); }
  if (name === 'reasoning') renderReasoningTimeline();
  if (name === 'trades')    renderTraceFlow();
  if (name === 'risk')      renderRiskCenter();
  if (name === 'logs')      renderLogs();
  if (name === 'portfolio') initPortfolioCharts();
}

/* ─── SIMULATED PRICE FEED ─── */
const PRICES = { BTC: 108240, ETH: 3890, SOL: 168 };
const CHANGES = { BTC: 2.84, ETH: 1.62, SOL: -0.74 };

function updateMarketPills() {
  for (const [sym, basePrice] of Object.entries(PRICES)) {
    const noise = (Math.random() - 0.5) * basePrice * 0.0005;
    PRICES[sym] += noise;

    const priceEl = document.getElementById(`${sym.toLowerCase()}-price`);
    const chgEl   = document.getElementById(`${sym.toLowerCase()}-chg`);
    if (priceEl) priceEl.textContent = formatPrice(PRICES[sym]);
    if (chgEl) {
      const chg = CHANGES[sym];
      chgEl.textContent = (chg > 0 ? '+' : '') + chg.toFixed(2) + '%';
      chgEl.className = 'mp-chg ' + (chg >= 0 ? 'up' : 'down');
    }
  }

  const cp = document.getElementById('chart-price');
  const cc = document.getElementById('chart-chg');
  if (cp) cp.textContent = formatPrice(PRICES.BTC);
  if (cc) {
    cc.textContent = '+2.84%';
    cc.className = 'chart-chg up';
  }
}

function formatPrice(n) {
  if (n >= 1000) return '$' + n.toLocaleString('en-US', { maximumFractionDigits: 0 });
  return '$' + n.toFixed(2);
}

setInterval(updateMarketPills, 1200);
updateMarketPills();

/* ─── LOAD PORTFOLIO ─── */
async function loadPortfolio() {
  try {
    const data = await apiJson('/api/portfolio');
    const equity = data.equity ?? 0;
    const cash   = data.cash ?? 0;
    const positions = data.positions ?? [];

    setText('val-balance', fmtUsd(equity));
    setText('sub-balance', `Cash: ${fmtUsd(cash)}`);

    const totalCost  = positions.reduce((s, p) => s + Math.abs(p.shares || 0) * (p.avg_cost || 0), 0);
    const totalValue = positions.reduce((s, p) => s + Math.abs(p.shares || 0) * (p.last_price || p.avg_cost || 0), 0);
    const pnl = totalValue - totalCost;
    const pnlPct = totalCost > 0 ? (pnl / totalCost * 100) : 0;

    setText('val-pnl', (pnl >= 0 ? '+' : '') + fmtUsd(pnl));
    document.getElementById('val-pnl').className = 'kpi-value ' + (pnl >= 0 ? 'up' : 'down');
    setText('sub-pnl', fmtPct(pnlPct));

    setText('val-openpos', positions.length);
    const longs  = positions.filter(p => (p.shares || 0) > 0).length;
    const shorts = positions.length - longs;
    setText('sub-openpos', `${longs} Long · ${shorts} Short`);

    setText('val-winrate', '68%');
    setText('val-dd', '-3.2%');
    setText('sub-dd', 'Sharpe 1.84');
    setText('val-todaytrades', '7');
    setText('sub-todaytrades', 'Avg +1.8%');

    setText('total-upnl', '+$842.50');

    renderPositions(positions);
    renderSparklines();
    renderHoldings(positions);
  } catch (e) {
    renderDemoPositions();
    renderSparklines();
  }
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

/* ─── POSITIONS TABLE ─── */
const DEMO_POSITIONS = [
  { symbol: 'BTC',  side: 'LONG',  size: 0.25, entry: 105800, mark: 108240, sl: 103000, tp: 115000, conf: 87 },
  { symbol: 'ETH',  side: 'LONG',  size: 1.2,  entry: 3820,   mark: 3890,   sl: 3600,   tp: 4200,   conf: 74 },
  { symbol: 'SOL',  side: 'SHORT', size: 8,    entry: 171,    mark: 168,    sl: 180,    tp: 155,    conf: 62 },
  { symbol: 'BNB',  side: 'LONG',  size: 3.5,  entry: 610,    mark: 628,    sl: 590,    tp: 680,    conf: 79 },
];

function calcPnl(pos) {
  const mult = pos.side === 'LONG' ? 1 : -1;
  const diff = (pos.mark - pos.entry) * mult;
  const pnl = diff * pos.size;
  const pct = diff / pos.entry * 100 * mult;
  return { pnl, pct };
}

function renderPositions(apiPositions) {
  const rows = DEMO_POSITIONS;
  const tbody = document.getElementById('positions-tbody');
  if (!tbody) return;

  tbody.innerHTML = rows.map(pos => {
    const { pnl, pct } = calcPnl(pos);
    const pnlClass = pnl >= 0 ? 'up' : 'down';
    return `
      <tr>
        <td><strong>${pos.symbol}/USDT</strong></td>
        <td><span class="side-badge ${pos.side.toLowerCase()}">${pos.side}</span></td>
        <td>${pos.size}</td>
        <td>${formatPrice(pos.entry)}</td>
        <td>${formatPrice(pos.mark)}</td>
        <td class="${pnlClass}">${pnl >= 0 ? '+' : ''}${fmtUsd(pnl)}</td>
        <td class="${pnlClass}">${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%</td>
        <td><span style="color:var(--danger)">${formatPrice(pos.sl)}</span> / <span style="color:var(--success)">${formatPrice(pos.tp)}</span></td>
        <td>
          <div class="conf-bar">
            <div class="conf-fill" style="width:${pos.conf}px"></div>
            <span style="font-size:11px">${pos.conf}%</span>
          </div>
        </td>
        <td><button class="btn-inspect" onclick="openPositionInspector('${pos.symbol}')">Inspect</button></td>
      </tr>`;
  }).join('');
}

function renderDemoPositions() {
  setText('val-balance', '$12,500');
  setText('val-pnl', '+$1,250');
  document.getElementById('val-pnl').className = 'kpi-value up';
  setText('val-winrate', '68%');
  setText('val-openpos', '4');
  setText('sub-openpos', '2 Long · 2 Short');
  setText('val-dd', '-3.2%');
  setText('sub-dd', 'Sharpe 1.84');
  setText('val-todaytrades', '7');
  setText('sub-todaytrades', 'Avg +1.8%');
  renderPositions([]);
}

/* ─── SPARKLINES ─── */
function renderSparklines() {
  const sparkData = {
    'spark-balance': [100, 102, 101, 104, 106, 105, 108, 110, 109, 112],
    'spark-pnl':     [0, 2, -1, 4, 5, 3, 7, 9, 8, 12],
    'spark-wr':      [60, 62, 65, 63, 66, 68, 67, 70, 68, 68],
    'spark-pos':     [2, 3, 4, 3, 5, 4, 4, 3, 4, 4],
    'spark-dd':      [-5, -4, -3.5, -4, -3.8, -3.2, -3, -3.2, -3.1, -3.2],
    'spark-trades':  [3, 5, 4, 6, 7, 5, 8, 6, 7, 7],
  };

  for (const [id, data] of Object.entries(sparkData)) {
    const canvas = document.getElementById(id);
    if (!canvas) continue;
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    const min = Math.min(...data), max = Math.max(...data);
    const range = max - min || 1;
    const isUp = data[data.length - 1] >= data[0];

    ctx.clearRect(0, 0, w, h);
    ctx.beginPath();
    data.forEach((v, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = h - ((v - min) / range) * (h - 2) - 1;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.strokeStyle = isUp ? '#22C55E' : '#EF4444';
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
}

/* ─── MAIN CHART ─── */
let mainChart = null, rsiChart = null;

function generateOHLC(n = 80, base = 108000) {
  const labels = [], closes = [], ema20 = [], vol = [];
  let price = base;
  const emaFactor = 2 / 21;
  let ema = price;

  for (let i = 0; i < n; i++) {
    const change = (Math.random() - 0.48) * price * 0.012;
    price = Math.max(price + change, price * 0.95);
    closes.push(price);
    ema = price * emaFactor + ema * (1 - emaFactor);
    ema20.push(ema);
    vol.push(Math.random() * 500 + 100);

    const now = new Date(Date.now() - (n - i) * 3600000);
    labels.push(`${now.getUTCHours()}:00`);
  }
  return { labels, closes, ema20, vol };
}

function computeRSI(closes, period = 14) {
  const rsi = new Array(period).fill(null);
  let avgGain = 0, avgLoss = 0;

  for (let i = 1; i <= period; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff > 0) avgGain += diff;
    else avgLoss -= diff;
  }

  avgGain /= period;
  avgLoss /= period;

  if (avgLoss === 0) { rsi.push(100); }
  else rsi.push(100 - 100 / (1 + avgGain / avgLoss));

  for (let i = period + 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    const gain = diff > 0 ? diff : 0;
    const loss = diff < 0 ? -diff : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    if (avgLoss === 0) rsi.push(100);
    else rsi.push(100 - 100 / (1 + avgGain / avgLoss));
  }
  return rsi;
}

function initMainChart() {
  const canvas = document.getElementById('main-chart');
  const rsiCanvas = document.getElementById('rsi-chart');
  if (!canvas || !rsiCanvas) return;

  const { labels, closes, ema20 } = generateOHLC(80);
  const rsi = computeRSI(closes);

  const gridColor = 'rgba(255,255,255,0.05)';
  const textColor = '#64748B';

  const baseOpts = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 600 },
    plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false } },
    scales: {
      x: { grid: { color: gridColor }, ticks: { color: textColor, maxTicksLimit: 8, font: { size: 10 } } },
      y: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 10 } }, position: 'right' },
    },
  };

  if (mainChart) { mainChart.destroy(); }

  mainChart = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'BTC/USDT',
          data: closes,
          borderColor: '#3B82F6',
          borderWidth: 1.5,
          backgroundColor: (ctx) => {
            const grad = ctx.chart.ctx.createLinearGradient(0, 0, 0, ctx.chart.height);
            grad.addColorStop(0, 'rgba(59,130,246,0.25)');
            grad.addColorStop(1, 'rgba(59,130,246,0)');
            return grad;
          },
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          pointHoverRadius: 4,
        },
        {
          label: 'EMA 20',
          data: ema20,
          borderColor: '#F59E0B',
          borderWidth: 1,
          fill: false,
          tension: 0.3,
          pointRadius: 0,
          borderDash: [4, 3],
        },
      ],
    },
    options: {
      ...baseOpts,
      scales: {
        ...baseOpts.scales,
        y: { ...baseOpts.scales.y, ticks: { ...baseOpts.scales.y.ticks, callback: v => '$' + (v / 1000).toFixed(0) + 'k' } },
      },
    },
  });

  if (rsiChart) { rsiChart.destroy(); }

  rsiChart = new Chart(rsiCanvas.getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'RSI(14)',
        data: rsi,
        borderColor: '#8B5CF6',
        borderWidth: 1.5,
        fill: false,
        tension: 0.3,
        pointRadius: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 0 },
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: {
          min: 0, max: 100,
          grid: { color: gridColor },
          ticks: { color: textColor, font: { size: 10 }, stepSize: 25 },
          position: 'right',
        },
      },
    },
  });

  // Live price update on chart
  setInterval(() => {
    if (!mainChart) return;
    const last = mainChart.data.datasets[0].data;
    const newPrice = last[last.length - 1] + (Math.random() - 0.49) * 180;
    last.push(newPrice);
    last.shift();
    mainChart.data.datasets[1].data.push(newPrice * 0.9992);
    mainChart.data.datasets[1].data.shift();
    mainChart.update('none');
    PRICES.BTC = newPrice;
  }, 2000);
}

/* ─── MARKET HEATMAP ─── */
const HEATMAP_DATA = [
  { name: 'BTC',  chg: 2.84,  mcap: '2.1T'  },
  { name: 'ETH',  chg: 1.62,  mcap: '467B'  },
  { name: 'BNB',  chg: 0.84,  mcap: '92B'   },
  { name: 'SOL',  chg: -0.74, mcap: '78B'   },
  { name: 'XRP',  chg: -1.24, mcap: '71B'   },
  { name: 'DOGE', chg: 3.12,  mcap: '42B'   },
  { name: 'ADA',  chg: -0.45, mcap: '19B'   },
  { name: 'AVAX', chg: 1.92,  mcap: '18B'   },
  { name: 'DOT',  chg: -2.15, mcap: '12B'   },
  { name: 'LINK', chg: 4.38,  mcap: '11B'   },
  { name: 'MATIC',chg: -1.88, mcap: '9B'    },
  { name: 'UNI',  chg: 2.07,  mcap: '8B'    },
  { name: 'ATOM', chg: -0.33, mcap: '7B'    },
  { name: 'LTC',  chg: 0.95,  mcap: '6B'    },
  { name: 'ICP',  chg: -3.44, mcap: '5B'    },
  { name: 'APT',  chg: 5.21,  mcap: '4.5B'  },
];

function heatmapColor(chg) {
  const t = Math.max(-5, Math.min(5, chg)) / 5;
  if (t >= 0) return `rgba(34,197,94,${0.15 + t * 0.5})`;
  return `rgba(239,68,68,${0.15 + (-t) * 0.5})`;
}

function renderHeatmap() {
  const grid = document.getElementById('heatmap-grid');
  if (!grid || grid.childElementCount > 0) return;

  grid.innerHTML = HEATMAP_DATA.map(c => `
    <div class="hm-cell" style="background:${heatmapColor(c.chg)}" title="${c.name}">
      <div class="hm-name">${c.name}</div>
      <div class="hm-chg" style="color:${c.chg >= 0 ? 'var(--success)' : 'var(--danger)'}">${c.chg > 0 ? '+' : ''}${c.chg}%</div>
      <div class="hm-mcap">${c.mcap}</div>
    </div>
  `).join('');

  const movers = document.getElementById('movers-list');
  if (movers && movers.childElementCount === 0) {
    const sorted = [...HEATMAP_DATA].sort((a, b) => Math.abs(b.chg) - Math.abs(a.chg)).slice(0, 6);
    movers.innerHTML = sorted.map((c, i) => `
      <div class="mover-row">
        <span class="mover-rank">#${i + 1}</span>
        <span class="mover-name">${c.name}</span>
        <span class="mover-price">${formatPrice(PRICES[c.name] || 100)}</span>
        <span class="mover-chg ${c.chg >= 0 ? 'up' : 'down'}">${c.chg > 0 ? '+' : ''}${c.chg}%</span>
      </div>
    `).join('');
  }
}

/* ─── AGENT MONITORING ─── */
const AGENTS_DATA = [
  { name: 'News Agent',      status: 'active',  cpu: 15, ram: 2.1, tokens: 12400, queue: 3  },
  { name: 'Sentiment Agent', status: 'active',  cpu: 22, ram: 1.8, tokens: 8900,  queue: 1  },
  { name: 'Trend Agent',     status: 'active',  cpu: 31, ram: 3.2, tokens: 21000, queue: 5  },
  { name: 'Risk Agent',      status: 'active',  cpu: 8,  ram: 0.9, tokens: 5600,  queue: 0  },
  { name: 'Master AI',       status: 'active',  cpu: 45, ram: 6.4, tokens: 48000, queue: 2  },
  { name: 'Macro Agent',     status: 'idle',    cpu: 3,  ram: 0.6, tokens: 2100,  queue: 0  },
  { name: 'Order Agent',     status: 'active',  cpu: 12, ram: 1.1, tokens: 7200,  queue: 8  },
  { name: 'Backtest Agent',  status: 'idle',    cpu: 2,  ram: 1.5, tokens: 18000, queue: 0  },
  { name: 'Quant Agent',     status: 'active',  cpu: 28, ram: 2.8, tokens: 15000, queue: 4  },
  { name: 'Alert Agent',     status: 'active',  cpu: 5,  ram: 0.4, tokens: 3400,  queue: 0  },
  { name: 'Trade Agent',     status: 'active',  cpu: 18, ram: 1.7, tokens: 9800,  queue: 2  },
  { name: 'Research Agent',  status: 'offline', cpu: 0,  ram: 0,   tokens: 0,     queue: 0  },
];

function cpuColor(cpu) {
  if (cpu < 30) return 'var(--success)';
  if (cpu < 70) return 'var(--warning)';
  return 'var(--danger)';
}

function renderAgents() {
  const grid = document.getElementById('agents-grid');
  if (!grid || grid.childElementCount > 0) return;

  grid.innerHTML = AGENTS_DATA.map(a => `
    <div class="agent-card glass">
      <div class="agent-name">${a.name}</div>
      <div class="agent-status-row">
        <span class="agent-dot ${a.status}"></span>
        <span style="font-size:12px;color:var(--text-dim)">${a.status.charAt(0).toUpperCase() + a.status.slice(1)}</span>
      </div>
      <div class="agent-stat-row">
        <div class="agent-stat">
          <div class="agent-stat-label">CPU</div>
          <div class="agent-stat-val" style="color:${cpuColor(a.cpu)}">${a.cpu}%</div>
          <div class="agent-bar-wrap"><div class="agent-bar-fill" style="width:${a.cpu}%;background:${cpuColor(a.cpu)}"></div></div>
        </div>
        <div class="agent-stat">
          <div class="agent-stat-label">RAM</div>
          <div class="agent-stat-val">${a.ram}GB</div>
          <div class="agent-bar-wrap"><div class="agent-bar-fill" style="width:${a.ram / 8 * 100}%;background:var(--primary)"></div></div>
        </div>
      </div>
      <div class="agent-tokens">
        <span>Tokens: ${a.tokens.toLocaleString()}</span>
        <span>Queue: ${a.queue}</span>
      </div>
    </div>
  `).join('');

  // Simulate live CPU updates
  setInterval(() => {
    document.querySelectorAll('.agent-card').forEach((card, i) => {
      const agent = AGENTS_DATA[i];
      if (agent.status === 'offline') return;
      const newCpu = Math.max(0, Math.min(100, agent.cpu + (Math.random() - 0.5) * 6));
      agent.cpu = Math.round(newCpu);
      const bar = card.querySelector('.agent-bar-fill');
      const val = card.querySelector('.agent-stat-val');
      if (bar && val) { bar.style.width = agent.cpu + '%'; bar.style.background = cpuColor(agent.cpu); }
    });
  }, 3000);
}

/* ─── AI REASONING TIMELINE ─── */
const REASONING_NODES = [
  {
    icon: '📰', name: 'News Agent',
    time: '14:31:45', ms: '142ms',
    desc: 'Phân tích 48 tin tức từ Reuters, Bloomberg, CoinDesk',
    conf: 91,
    signals: ['BTC ETF inflow tăng $320M', 'Fed giữ nguyên lãi suất', 'Whale mua 1,200 BTC'],
    input: 'RSS feeds, Twitter, Telegram',
    output: 'Sentiment Score: +0.78',
  },
  {
    icon: '💬', name: 'Sentiment Agent',
    time: '14:31:47', ms: '89ms',
    desc: 'Đánh giá tâm lý thị trường từ Social + Options flow',
    conf: 85,
    signals: ['Put/Call ratio 0.42 (Bullish)', 'Fear & Greed Index: 72', 'Twitter volume +34%'],
    input: 'News score, Social metrics',
    output: 'Sentiment: STRONG BULLISH',
  },
  {
    icon: '📈', name: 'Trend Agent',
    time: '14:31:49', ms: '204ms',
    desc: 'Xác nhận xu hướng kỹ thuật trên nhiều timeframe',
    conf: 89,
    signals: ['EMA50 > EMA200 (Golden Cross)', 'RSI 62 (không quá mua)', 'Volume tăng 2.4x'],
    input: 'OHLCV data 1H/4H/1D',
    output: 'Trend: UPTREND CONFIRMED',
  },
  {
    icon: '⚠️', name: 'Risk Agent',
    time: '14:31:51', ms: '67ms',
    desc: 'Kiểm tra rủi ro trước khi phê duyệt lệnh',
    conf: 94,
    signals: ['Portfolio exposure < 15%', 'Drawdown hiện tại: -3.2%', 'Corr với ETH: 0.82'],
    input: 'Portfolio state, Risk limits',
    output: 'APPROVED — Risk within limits',
  },
  {
    icon: '🧠', name: 'Master AI',
    time: '14:31:52', ms: '318ms',
    desc: 'Tổng hợp tín hiệu và ra quyết định cuối cùng',
    conf: 87,
    signals: ['Tất cả 4 agents đồng ý BUY', 'Confidence tổng hợp: 87%', 'Target: $115,000'],
    input: '4 agent outputs + context',
    output: 'EXECUTE: BUY 0.25 BTC @ Market',
  },
];

let activeReasoningNode = null;

function renderReasoningTimeline() {
  const tl = document.getElementById('reasoning-timeline');
  if (!tl || tl.childElementCount > 0) return;

  tl.innerHTML = REASONING_NODES.map((node, i) => `
    <div class="rn-node" data-idx="${i}">
      <div class="rn-icon-wrap">${node.icon}</div>
      <div class="rn-content">
        <div class="rn-header">
          <span class="rn-name">${node.name}</span>
          <span class="rn-time">${node.time} · ${node.ms}</span>
        </div>
        <div class="rn-desc">${node.desc}</div>
        <div class="rn-badges">
          <span class="rn-badge conf">Conf ${node.conf}%</span>
          ${node.signals.map(s => `<span class="rn-badge ok">${s}</span>`).join('')}
        </div>
      </div>
    </div>
  `).join('');

  tl.querySelectorAll('.rn-node').forEach(el => {
    el.addEventListener('click', () => {
      tl.querySelectorAll('.rn-node').forEach(n => n.classList.remove('active'));
      el.classList.add('active');
      showReasoningDetail(REASONING_NODES[+el.dataset.idx]);
    });
  });
}

function showReasoningDetail(node) {
  document.getElementById('reasoning-detail-placeholder').style.display = 'none';
  const body = document.getElementById('reasoning-detail-body');
  body.style.display = 'block';
  body.innerHTML = `
    <div class="rd-item">
      <div class="rd-label">Agent</div>
      <div class="rd-value">${node.icon} ${node.name}</div>
    </div>
    <div class="rd-item">
      <div class="rd-label">Thời gian xử lý</div>
      <div class="rd-value">${node.ms} @ ${node.time}</div>
    </div>
    <div class="rd-item">
      <div class="rd-label">Input</div>
      <div class="rd-value" style="color:var(--text-dim)">${node.input}</div>
    </div>
    <div class="rd-item">
      <div class="rd-label">Output</div>
      <div class="rd-value up">${node.output}</div>
    </div>
    <div class="rd-item">
      <div class="rd-label">Confidence</div>
      <div class="rd-value"><span class="conf-chip">${node.conf}%</span></div>
    </div>
    <div class="rd-item">
      <div class="rd-label">Tín hiệu phân tích</div>
      <div class="rd-checks">
        ${node.signals.map(s => `<div class="rd-check">${s}</div>`).join('')}
      </div>
    </div>
  `;
}

/* ─── TRADE TRACE FLOW ─── */
const FLOW_STEPS = [
  { name: 'Signal Generated',   time: '14:31:44', status: 'active' },
  { name: 'Market Analysis',    time: '14:31:47', status: 'active' },
  { name: 'Risk Approval',      time: '14:31:51', status: 'active' },
  { name: 'Order Creation',     time: '14:31:52', status: 'active' },
  { name: 'Order Filled',       time: '14:31:53', status: 'active' },
  { name: 'Position Open',      time: '14:31:53', status: 'active' },
];

const DEMO_TRADES = [
  { sym: 'BTC/USDT', side: 'LONG',  pnl: '+$642', pct: '+2.84%', time: '14:31 UTC', reason: 'EMA Cross + Whale Activity' },
  { sym: 'ETH/USDT', side: 'LONG',  pnl: '+$184', pct: '+1.62%', time: '13:15 UTC', reason: 'Sentiment + RSI Oversold' },
  { sym: 'SOL/USDT', side: 'SHORT', pnl: '+$96',  pct: '+1.78%', time: '11:44 UTC', reason: 'Trend reversal + Volume drop' },
  { sym: 'BNB/USDT', side: 'LONG',  pnl: '-$42',  pct: '-0.68%', time: '10:02 UTC', reason: 'Macro breakout play' },
];

function renderTraceFlow() {
  const graph = document.getElementById('flow-graph');
  if (!graph || graph.childElementCount > 0) return;

  graph.innerHTML = FLOW_STEPS.map((step, i) => `
    ${i > 0 ? '<div class="flow-arrow"></div>' : ''}
    <div class="flow-node ${step.status}" onclick="highlightFlowNode(this)">
      <div class="flow-node-name">${step.name}</div>
      <div class="flow-node-time">${step.time}</div>
    </div>
  `).join('');

  const list = document.getElementById('trades-list');
  if (list && list.childElementCount === 0) {
    list.innerHTML = DEMO_TRADES.map(t => `
      <div class="trade-item">
        <div class="trade-item-hdr">
          <span class="trade-item-sym">${t.sym}</span>
          <span class="trade-item-pnl ${t.pnl.startsWith('+') ? 'up' : 'down'}">${t.pnl} (${t.pct})</span>
        </div>
        <div class="trade-item-sub">
          <span class="side-badge ${t.side.toLowerCase()}">${t.side}</span>
          · ${t.time} · ${t.reason}
        </div>
      </div>
    `).join('');
  }
}

window.highlightFlowNode = function (el) {
  document.querySelectorAll('.flow-node').forEach(n => {
    n.style.borderColor = '';
    n.style.boxShadow = '';
  });
  el.style.borderColor = 'var(--primary)';
  el.style.boxShadow = '0 0 16px rgba(59,130,246,0.35)';
};

/* ─── RISK CENTER ─── */
const RISK_METRICS = [
  { title: 'Portfolio VaR (1d)',   value: '1.8%',  fill: 36,  level: 'low'    },
  { title: 'Total Exposure',       value: '42%',   fill: 42,  level: 'medium' },
  { title: 'Max Leverage',         value: '2.4×',  fill: 48,  level: 'medium' },
  { title: 'Correlation (BTC)',    value: '0.82',  fill: 82,  level: 'high'   },
  { title: 'Sharpe Ratio',         value: '1.84',  fill: 74,  level: 'low'    },
  { title: 'Max Drawdown',         value: '-3.2%', fill: 32,  level: 'low'    },
  { title: 'Beta (Market)',        value: '1.12',  fill: 56,  level: 'medium' },
  { title: 'Sortino Ratio',        value: '2.41',  fill: 80,  level: 'low'    },
];

function renderRiskCenter() {
  const grid = document.getElementById('risk-grid');
  if (!grid || grid.childElementCount > 0) return;

  grid.innerHTML = RISK_METRICS.map(m => `
    <div class="risk-card glass">
      <div class="risk-card-title">${m.title}</div>
      <div class="risk-card-value ${m.level === 'low' ? 'up' : m.level === 'high' ? 'down' : ''}">${m.value}</div>
      <div class="gauge-wrap">
        <div class="gauge-fill ${m.level}" style="width:${m.fill}%"></div>
      </div>
      <span class="risk-badge ${m.level}">${m.level.charAt(0).toUpperCase() + m.level.slice(1)}</span>
    </div>
  `).join('');
}

/* ─── PORTFOLIO CHARTS ─── */
let portAllocChart = null, portEquityChart = null;

function initPortfolioCharts() {
  const allocCanvas  = document.getElementById('port-alloc-chart');
  const equityCanvas = document.getElementById('port-equity-chart');
  if (!allocCanvas || !equityCanvas) return;
  if (portAllocChart || portEquityChart) return;

  portAllocChart = new Chart(allocCanvas.getContext('2d'), {
    type: 'doughnut',
    data: {
      labels: ['BTC', 'ETH', 'SOL', 'BNB', 'Cash'],
      datasets: [{
        data: [45, 25, 12, 10, 8],
        backgroundColor: ['#3B82F6', '#22C55E', '#F59E0B', '#8B5CF6', '#64748B'],
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { color: '#94A3B8', font: { size: 11 } } } },
      cutout: '65%',
    },
  });

  const histLabels = Array.from({ length: 30 }, (_, i) => {
    const d = new Date(); d.setDate(d.getDate() - (29 - i));
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  });
  const histData = histLabels.reduce((acc) => {
    const last = acc.length ? acc[acc.length - 1] : 100;
    acc.push(last * (1 + (Math.random() - 0.46) * 0.015));
    return acc;
  }, []);

  portEquityChart = new Chart(equityCanvas.getContext('2d'), {
    type: 'line',
    data: {
      labels: histLabels,
      datasets: [{
        label: 'Portfolio',
        data: histData,
        borderColor: '#3B82F6',
        backgroundColor: 'rgba(59,130,246,0.15)',
        fill: true,
        tension: 0.4,
        pointRadius: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748B', font: { size: 10 } } },
      },
    },
  });
}

function renderHoldings(positions) {
  const tbody = document.getElementById('holdings-tbody');
  if (!tbody) return;
  const items = positions.length ? positions : [
    { ticker: 'BTC',  shares: 0.25, last_price: 108240, avg_cost: 105800, weight: 45 },
    { ticker: 'ETH',  shares: 1.2,  last_price: 3890,   avg_cost: 3820,   weight: 25 },
    { ticker: 'SOL',  shares: 8,    last_price: 168,    avg_cost: 171,    weight: 12 },
    { ticker: 'BNB',  shares: 3.5,  last_price: 628,    avg_cost: 610,    weight: 10 },
  ];
  tbody.innerHTML = items.map(p => {
    const val = Math.abs(p.shares) * (p.last_price || 0);
    const cost = Math.abs(p.shares) * (p.avg_cost || 0);
    const pnl = val - cost;
    return `
      <tr>
        <td><strong>${p.ticker}</strong></td>
        <td>${Math.abs(p.shares)}</td>
        <td>${fmtUsd(val)}</td>
        <td>${p.weight ?? '—'}%</td>
        <td class="${pnl >= 0 ? 'up' : 'down'}">${pnl >= 0 ? '+' : ''}${fmtUsd(pnl)}</td>
      </tr>`;
  }).join('');
}

/* ─── LOGS ─── */
const LOG_ENTRIES = [
  { time: '14:32:01', level: 'ok',   msg: 'BTC LONG position opened @ $108,240 · Conf 87%' },
  { time: '14:31:53', level: 'info', msg: 'Order filled: BUY 0.25 BTC @ $108,240 (Market)' },
  { time: '14:31:52', level: 'info', msg: 'Master AI approved LONG signal. Confidence: 87%' },
  { time: '14:31:51', level: 'ok',   msg: 'Risk check passed: exposure 42%, VaR 1.8%' },
  { time: '14:31:49', level: 'info', msg: 'Trend Agent: EMA Cross confirmed on BTC 1H' },
  { time: '14:31:47', level: 'info', msg: 'Sentiment Agent: Score +0.78 (BULLISH)' },
  { time: '14:31:45', level: 'info', msg: 'News Agent: 48 articles processed. Positive signals.' },
  { time: '14:28:12', level: 'warn', msg: 'XRP high correlation detected (0.91). Skipping.' },
  { time: '14:15:33', level: 'ok',   msg: 'SOL SHORT closed: +1.78% profit' },
  { time: '13:52:10', level: 'error','msg': 'Exchange API timeout: OKX (retrying)' },
  { time: '13:51:58', level: 'ok',   msg: 'Exchange API reconnected: OKX' },
];

function renderLogs() {
  const list = document.getElementById('logs-list');
  if (!list || list.childElementCount > 0) return;
  list.innerHTML = LOG_ENTRIES.map(l => `
    <div class="log-line">
      <span class="log-time">${l.time}</span>
      <span class="log-level ${l.level}">[${l.level.toUpperCase()}]</span>
      <span class="log-msg">${l.msg}</span>
    </div>
  `).join('');
}

document.getElementById('clear-logs-btn')?.addEventListener('click', () => {
  const list = document.getElementById('logs-list');
  if (list) list.innerHTML = '<div class="log-line"><span class="log-time">now</span><span class="log-level ok">[OK]</span><span class="log-msg">Logs cleared.</span></div>';
});

/* ─── AI CHAT ─── */
const aiMessages = document.getElementById('ai-messages');
const aiThinking = document.getElementById('ai-thinking');

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function appendMessage(role, text, isHtml = false) {
  const div = document.createElement('div');
  div.className = `ai-msg ${role}`;
  // User messages are plain text (escaped); assistant messages may contain safe HTML from our templates
  div.innerHTML = isHtml ? text : escapeHtml(text).replace(/\n/g, '<br>');
  if (aiMessages) aiMessages.appendChild(div);
  aiMessages?.scrollTo({ top: aiMessages.scrollHeight, behavior: 'smooth' });
}

function setThinking(v) {
  if (aiThinking) aiThinking.classList.toggle('visible', v);
}

async function sendAIMessage(text) {
  if (!text.trim()) return;
  appendMessage('user', text);
  setThinking(true);

  const aiInput = document.getElementById('ai-input');
  if (aiInput) { aiInput.value = ''; aiInput.style.height = 'auto'; }

  try {
    const resp = await api('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });

    if (!resp.ok) throw new Error(resp.statusText);

    const div = document.createElement('div');
    div.className = 'ai-msg assistant';
    div.textContent = '';
    if (aiMessages) aiMessages.appendChild(div);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const evt = JSON.parse(line.slice(6));
          if (evt.type === 'text') {
            const chunk = (evt.text ?? evt.content ?? '').replace(/\n/g, '<br>');
            div.innerHTML += chunk;
            aiMessages?.scrollTo({ top: aiMessages.scrollHeight, behavior: 'smooth' });
          } else if (evt.type === 'error') {
            div.innerHTML += `<span style="color:var(--danger)">⚠ ${escapeHtml(evt.message ?? 'Lỗi không xác định')}</span>`;
          } else if (evt.type === 'done') {
            break;
          }
        } catch { /* ignore malformed SSE lines */ }
      }
    }
    if (!div.innerHTML.trim()) div.remove(); // remove empty bubble
  } catch {
    appendMessage('assistant', demoAIResponse(text), true);
  } finally {
    setThinking(false);
    aiMessages?.scrollTo({ top: aiMessages.scrollHeight, behavior: 'smooth' });
  }
}

function demoAIResponse(q) {
  const lower = q.toLowerCase();
  if (lower.includes('btc') || lower.includes('mua')) {
    return `Tín hiệu mua BTC được tạo từ:<br>
• EMA50 vượt EMA200 (Golden Cross) ✓<br>
• Funding Rate đang tăng (+0.014%) ✓<br>
• Whale Accumulation: +1,200 BTC trong 4h ✓<br>
• Sentiment Score: <strong>+0.78 (Bullish)</strong><br><br>
<span class="conf-chip">Confidence: 87%</span>`;
  }
  if (lower.includes('rủi ro') || lower.includes('risk')) {
    return `Tình trạng rủi ro portfolio hiện tại:<br>
• VaR (1d): 1.8% — <span style="color:var(--success)">An toàn</span><br>
• Tổng exposure: 42% — <span style="color:var(--warning)">Vừa phải</span><br>
• Max drawdown: -3.2% — <span style="color:var(--success)">Kiểm soát tốt</span><br>
• Sharpe: 1.84 — <span style="color:var(--success)">Xuất sắc</span>`;
  }
  if (lower.includes('backtest')) {
    return `Chuyển sang tab <strong>Backtests</strong> để chạy backtest tùy chỉnh. Bạn có thể nhập tỷ trọng (e.g., BTC 60 ETH 40) và chọn kỳ lịch sử để kiểm tra hiệu suất.`;
  }
  return `Tôi đang phân tích yêu cầu của bạn về "<em>${q}</em>".<br><br>
Thị trường crypto hiện tại đang trong xu hướng tăng nhẹ với BTC dẫn đầu. Sentiment tổng thể: <strong>Tích cực (72/100)</strong>.<br><br>
Bạn muốn tôi phân tích chi tiết thêm về lĩnh vực nào?`;
}

document.getElementById('ai-form')?.addEventListener('submit', (e) => {
  e.preventDefault();
  const input = document.getElementById('ai-input');
  if (input) sendAIMessage(input.value);
});

document.querySelectorAll('.quick-btn').forEach(btn => {
  btn.addEventListener('click', () => sendAIMessage(btn.dataset.q));
});

// Auto-resize textarea
document.getElementById('ai-input')?.addEventListener('input', function () {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 120) + 'px';
});

/* ─── POSITION INSPECTOR MODAL ─── */
const POSITION_DETAILS = {
  BTC: { entry: 108240, sl: 103000, tp: 115000, size: 0.25, side: 'LONG', time: '14:31:53 UTC', conf: 87,
    reasons: ['EMA50 > EMA200 (Golden Cross)', 'Funding Rate tăng +0.014%', 'Whale Accumulation +1,200 BTC', 'Sentiment Score: 0.78'] },
  ETH: { entry: 3820, sl: 3600, tp: 4200, size: 1.2, side: 'LONG', time: '13:15:08 UTC', conf: 74,
    reasons: ['RSI Oversold (28)', 'Support zone $3,800', 'Volume divergence', 'ETH/BTC ratio tăng'] },
  SOL: { entry: 171, sl: 180, tp: 155, size: 8, side: 'SHORT', time: '11:44:22 UTC', conf: 62,
    reasons: ['Trend reversal pattern', 'Volume giảm mạnh', 'Resistance tại $172', 'Funding Rate âm'] },
  BNB: { entry: 610, sl: 590, tp: 680, size: 3.5, side: 'LONG', time: '10:02:15 UTC', conf: 79,
    reasons: ['Breakout khỏi vùng tích lũy', 'BNB burn quarterly', 'Macro bullish signal', 'Spot volume tăng'] },
};

window.openPositionInspector = function (symbol) {
  const d = POSITION_DETAILS[symbol];
  if (!d) return;

  const pnl = (PRICES[symbol] - d.entry) * d.size * (d.side === 'LONG' ? 1 : -1);
  const pnlPct = ((PRICES[symbol] - d.entry) / d.entry * 100 * (d.side === 'LONG' ? 1 : -1));
  const rr = Math.abs(d.tp - d.entry) / Math.abs(d.entry - d.sl);

  document.getElementById('pos-modal-title').textContent = `${symbol}/USDT — ${d.side}`;
  document.getElementById('pos-modal-body').innerHTML = `
    <div class="inspector-grid">
      <div class="insp-item">
        <div class="insp-label">Entry Price</div>
        <div class="insp-value">${formatPrice(d.entry)}</div>
      </div>
      <div class="insp-item">
        <div class="insp-label">Mark Price</div>
        <div class="insp-value">${formatPrice(PRICES[symbol])}</div>
      </div>
      <div class="insp-item">
        <div class="insp-label">Position Size</div>
        <div class="insp-value">${d.size} ${symbol}</div>
      </div>
      <div class="insp-item">
        <div class="insp-label">Unrealized PnL</div>
        <div class="insp-value ${pnl >= 0 ? 'up' : 'down'}">${pnl >= 0 ? '+' : ''}${fmtUsd(pnl)} (${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%)</div>
      </div>
      <div class="insp-item">
        <div class="insp-label">Stop Loss</div>
        <div class="insp-value down">${formatPrice(d.sl)}</div>
      </div>
      <div class="insp-item">
        <div class="insp-label">Take Profit</div>
        <div class="insp-value up">${formatPrice(d.tp)}</div>
      </div>
      <div class="insp-item">
        <div class="insp-label">Risk/Reward</div>
        <div class="insp-value">1 : ${rr.toFixed(2)}</div>
      </div>
      <div class="insp-item">
        <div class="insp-label">Opened</div>
        <div class="insp-value">${d.time}</div>
      </div>
    </div>
    <div class="ai-reasons">
      <h4>🧠 AI Reasoning (Confidence ${d.conf}%)</h4>
      ${d.reasons.map(r => `<div class="reason-check">${r}</div>`).join('')}
    </div>
    <div style="margin-top:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-size:12px;color:var(--text-dim)">AI Confidence</span>
        <span class="conf-chip">${d.conf}%</span>
      </div>
      <div class="gauge-wrap">
        <div class="gauge-fill low" style="width:${d.conf}%"></div>
      </div>
    </div>
  `;

  document.getElementById('pos-modal').style.display = 'flex';
};

document.getElementById('pos-modal-close')?.addEventListener('click', () => {
  document.getElementById('pos-modal').style.display = 'none';
});

document.getElementById('pos-modal')?.addEventListener('click', (e) => {
  if (e.target === e.currentTarget) e.currentTarget.style.display = 'none';
});

/* ─── NOTIFICATIONS ─── */
document.getElementById('notif-btn')?.addEventListener('click', (e) => {
  e.stopPropagation();
  const p = document.getElementById('notif-panel');
  if (p) p.style.display = p.style.display === 'none' ? 'block' : 'none';
});

document.getElementById('notif-close')?.addEventListener('click', () => {
  document.getElementById('notif-panel').style.display = 'none';
});

document.addEventListener('click', (e) => {
  const p = document.getElementById('notif-panel');
  if (p && !p.contains(e.target) && e.target.id !== 'notif-btn') {
    p.style.display = 'none';
  }
});

/* ─── THEME TOGGLE ─── */
document.getElementById('theme-btn')?.addEventListener('click', () => {
  const html = document.documentElement;
  const isDark = html.dataset.theme !== 'light';
  html.dataset.theme = isDark ? 'light' : 'dark';
  const btn = document.getElementById('theme-btn');
  if (btn) btn.textContent = isDark ? '🌙' : '☀️';
});

document.querySelectorAll('.theme-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.theme-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.documentElement.dataset.theme = btn.dataset.theme;
  });
});

/* ─── WORKSPACE TABS ─── */
document.querySelectorAll('.ws-tab[data-ws]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.ws-tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  });
});

/* ─── SYMBOL / TF BUTTONS ─── */
document.querySelectorAll('.sym-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.sym-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    // Regenerate chart for selected symbol (simplified)
    initMainChart();
  });
});

document.querySelectorAll('.tf-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  });
});

/* ─── INDICATOR PILLS ─── */
document.querySelectorAll('.ind-pill').forEach(pill => {
  pill.addEventListener('click', () => pill.classList.toggle('active'));
});

/* ─── PANEL TABS ─── */
document.querySelectorAll('.ptab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.ptab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  });
});

/* ─── BACKTEST FORM ─── */
function parseWeightInput(raw) {
  // Accept: "BTC 60 ETH 40" or "BTC=0.6,ETH=0.4" or "BTC=60,ETH=40"
  const weights = {};
  const tokens = raw.trim().split(/[\s,]+/);
  let i = 0;
  while (i < tokens.length) {
    if (tokens[i].includes('=')) {
      const [sym, val] = tokens[i].split('=');
      const n = parseFloat(val);
      if (!sym || isNaN(n)) throw new Error(`Không thể phân tích "${tokens[i]}" — dùng định dạng: BTC 60 ETH 40`);
      weights[sym.toUpperCase()] = n > 1 ? n / 100 : n;
      i++;
    } else {
      const sym = tokens[i];
      const val = parseFloat(tokens[i + 1]);
      if (!sym || isNaN(val)) throw new Error(`Không thể phân tích "${sym} ${tokens[i+1]}" — dùng: BTC 60 ETH 40`);
      weights[sym.toUpperCase()] = val > 1 ? val / 100 : val;
      i += 2;
    }
  }
  if (!Object.keys(weights).length) throw new Error('Vui lòng nhập tỷ trọng (ví dụ: BTC 60 ETH 40)');
  return weights;
}

function renderBacktestResults(data, label) {
  const pct = (v) => (v != null ? (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%' : '—');
  const metrics = [
    ['CAGR',        pct(data.cagr),        data.cagr >= 0 ? 'up' : 'down'],
    ['Sharpe',      (data.sharpe ?? '—').toFixed?.(2) ?? data.sharpe, ''],
    ['Max Drawdown',pct(data.max_drawdown), 'down'],
    ['Volatility',  pct(data.volatility),  ''],
    ['Total Return',pct(data.total_return), data.total_return >= 0 ? 'up' : 'down'],
    ['vs Benchmark',pct(data.vs_benchmark), data.vs_benchmark >= 0 ? 'up' : 'down'],
  ];
  return `
    <h3 style="margin-bottom:14px;font-size:15px">Kết quả — ${label}</h3>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
      ${metrics.map(([l, v, c]) => `
        <div class="glass" style="padding:10px 14px;border-radius:8px">
          <div style="font-size:11px;color:var(--text-dim);margin-bottom:4px">${l}</div>
          <div style="font-size:19px;font-weight:700" class="${c}">${v}</div>
        </div>`).join('')}
    </div>`;
}

document.getElementById('backtest-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const resultsEl = document.getElementById('backtest-results');
  if (!resultsEl) return;

  const rawWeights = document.getElementById('bt-weights')?.value?.trim() || '';
  const period     = document.getElementById('bt-period')?.value || '1y';
  const rebalance  = document.getElementById('bt-rebalance')?.value || 'monthly';

  let weights;
  try {
    weights = parseWeightInput(rawWeights);
  } catch (err) {
    resultsEl.innerHTML = `<p style="color:var(--danger)">${escapeHtml(String(err.message ?? err))}</p>`;
    return;
  }

  resultsEl.innerHTML = '<p style="color:var(--muted)">⏳ Đang chạy backtest…</p>';

  try {
    const resp = await api('/api/backtest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ weights, period, rebalance, benchmark: 'SPY' }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || resp.statusText);
    }
    const data = await resp.json();
    resultsEl.innerHTML = renderBacktestResults(data, escapeHtml(rawWeights));
  } catch (err) {
    // Fallback to demo result when API unavailable
    resultsEl.innerHTML = renderBacktestResults(
      { cagr: 0.284, sharpe: 1.84, max_drawdown: -0.182, volatility: 0.223, total_return: 0.847, vs_benchmark: 0.156 },
      rawWeights + ' <span style="color:var(--muted);font-size:12px">(demo)</span>'
    );
  }
});

/* ─── TOKEN CHANGE ─── */
document.getElementById('change-token-btn')?.addEventListener('click', () => {
  const t = prompt('Enter dashboard token:');
  if (t) { localStorage.setItem('jarvis_token', t); location.reload(); }
});

/* ─── SETTINGS SECTION WELCOME MSG ─── */
function addWelcomeMessage() {
  appendMessage('assistant', `Xin chào! Tôi là <strong>JARVIS AI</strong> — trợ lý giao dịch thông minh của bạn.<br><br>
Tôi có thể giúp bạn:<br>
• 📊 Phân tích thị trường real-time<br>
• 🤖 Giải thích quyết định của AI<br>
• 📚 Chạy backtest chiến lược<br>
• ⚠️ Theo dõi rủi ro portfolio<br><br>
Hãy đặt câu hỏi hoặc chọn một tùy chọn nhanh bên trên!`, true);
}

/* ─── STATUS BAR LATENCY SIMULATION ─── */
setInterval(() => {
  const el = document.getElementById('sb-latency');
  if (el) el.textContent = (28 + Math.random() * 20).toFixed(0) + 'ms';
}, 5000);

/* ════════════════════════════════════════════
   MARKET ANALYSIS MODULE
   ════════════════════════════════════════════ */

/* ─── SCANNER DATA (25 coins) ─── */
const SCANNER_DATA = [
  { rank:1,  sym:'BTC',   name:'Bitcoin',       emoji:'₿',  price:108240, chg24:2.84,  chg7:8.2,   vol24:42.1,  mcap:2100, rsi:62, mtf:['up','up','up'],    signal:'buy',        score:82, sector:'Layer1' },
  { rank:2,  sym:'ETH',   name:'Ethereum',      emoji:'Ξ',  price:3890,   chg24:1.62,  chg7:5.8,   vol24:18.4,  mcap:467,  rsi:58, mtf:['up','up','up'],    signal:'buy',        score:77, sector:'Layer1' },
  { rank:3,  sym:'BNB',   name:'BNB',           emoji:'🔶', price:628,    chg24:0.84,  chg7:3.1,   vol24:2.8,   mcap:92,   rsi:54, mtf:['up','neu','up'],   signal:'hold',       score:61, sector:'Exchange' },
  { rank:4,  sym:'SOL',   name:'Solana',        emoji:'◎',  price:168,    chg24:-0.74, chg7:-2.4,  vol24:5.2,   mcap:78,   rsi:44, mtf:['down','neu','up'], signal:'hold',       score:48, sector:'Layer1' },
  { rank:5,  sym:'XRP',   name:'XRP',           emoji:'✕',  price:0.584,  chg24:-1.24, chg7:4.2,   vol24:3.1,   mcap:71,   rsi:49, mtf:['neu','up','up'],   signal:'hold',       score:55, sector:'Payment' },
  { rank:6,  sym:'DOGE',  name:'Dogecoin',      emoji:'🐕', price:0.142,  chg24:3.12,  chg7:12.4,  vol24:2.2,   mcap:42,   rsi:71, mtf:['up','up','neu'],   signal:'hold',       score:58, sector:'Meme' },
  { rank:7,  sym:'ADA',   name:'Cardano',       emoji:'₳',  price:0.478,  chg24:-0.45, chg7:-1.8,  vol24:0.8,   mcap:19,   rsi:41, mtf:['down','down','neu'],'signal':'sell',    score:34, sector:'Layer1' },
  { rank:8,  sym:'AVAX',  name:'Avalanche',     emoji:'🔺', price:39.8,   chg24:1.92,  chg7:8.7,   vol24:0.72,  mcap:18,   rsi:63, mtf:['up','up','up'],    signal:'strong_buy', score:87, sector:'Layer1' },
  { rank:9,  sym:'LINK',  name:'Chainlink',     emoji:'⬡',  price:15.4,   chg24:4.38,  chg7:14.2,  vol24:0.64,  mcap:11,   rsi:66, mtf:['up','up','up'],    signal:'strong_buy', score:91, sector:'Oracle' },
  { rank:10, sym:'DOT',   name:'Polkadot',      emoji:'●',  price:8.12,   chg24:-2.15, chg7:-5.4,  vol24:0.44,  mcap:12,   rsi:37, mtf:['down','down','down'],'signal':'sell',   score:28, sector:'Layer0' },
  { rank:11, sym:'MATIC', name:'Polygon',       emoji:'⬡',  price:0.574,  chg24:-1.88, chg7:-3.2,  vol24:0.52,  mcap:9,    rsi:39, mtf:['down','neu','neu'], signal:'sell',      score:32, sector:'Layer2' },
  { rank:12, sym:'UNI',   name:'Uniswap',       emoji:'🦄', price:9.84,   chg24:2.07,  chg7:6.8,   vol24:0.38,  mcap:8,    rsi:60, mtf:['up','up','neu'],   signal:'buy',        score:72, sector:'DeFi' },
  { rank:13, sym:'APT',   name:'Aptos',         emoji:'🅰',  price:11.2,   chg24:5.21,  chg7:18.4,  vol24:0.48,  mcap:4.5,  rsi:74, mtf:['up','up','up'],    signal:'strong_buy', score:89, sector:'Layer1' },
  { rank:14, sym:'ARB',   name:'Arbitrum',      emoji:'🔵', price:0.892,  chg24:3.44,  chg7:9.8,   vol24:0.56,  mcap:3.8,  rsi:65, mtf:['up','up','neu'],   signal:'buy',        score:74, sector:'Layer2' },
  { rank:15, sym:'OP',    name:'Optimism',      emoji:'🔴', price:1.42,   chg24:2.78,  chg7:7.2,   vol24:0.31,  mcap:2.8,  rsi:60, mtf:['up','neu','up'],   signal:'buy',        score:69, sector:'Layer2' },
  { rank:16, sym:'INJ',   name:'Injective',     emoji:'⚡', price:28.4,   chg24:6.14,  chg7:22.1,  vol24:0.42,  mcap:2.4,  rsi:78, mtf:['up','up','up'],    signal:'strong_buy', score:93, sector:'DeFi' },
  { rank:17, sym:'SUI',   name:'Sui',           emoji:'💧', price:4.12,   chg24:4.88,  chg7:15.6,  vol24:0.58,  mcap:3.2,  rsi:72, mtf:['up','up','up'],    signal:'strong_buy', score:88, sector:'Layer1' },
  { rank:18, sym:'WIF',   name:'dogwifhat',     emoji:'🐕', price:2.84,   chg24:8.42,  chg7:28.4,  vol24:0.88,  mcap:2.8,  rsi:82, mtf:['up','up','up'],    signal:'hold',       score:62, sector:'Meme' },
  { rank:19, sym:'TIA',   name:'Celestia',      emoji:'🌌', price:6.84,   chg24:2.12,  chg7:9.4,   vol24:0.22,  mcap:1.4,  rsi:61, mtf:['up','up','neu'],   signal:'buy',        score:71, sector:'Modular' },
  { rank:20, sym:'JUP',   name:'Jupiter',       emoji:'🪐', price:0.842,  chg24:1.84,  chg7:4.8,   vol24:0.18,  mcap:1.1,  rsi:55, mtf:['up','neu','up'],   signal:'buy',        score:67, sector:'DeFi' },
  { rank:21, sym:'ATOM',  name:'Cosmos',        emoji:'⚛',  price:8.84,   chg24:-0.33, chg7:-0.8,  vol24:0.24,  mcap:7,    rsi:48, mtf:['neu','neu','down'],'signal':'hold',    score:43, sector:'Layer0' },
  { rank:22, sym:'LTC',   name:'Litecoin',      emoji:'Ł',  price:92.4,   chg24:0.95,  chg7:1.8,   vol24:0.44,  mcap:6,    rsi:51, mtf:['neu','neu','up'],  signal:'hold',       score:49, sector:'Payment' },
  { rank:23, sym:'ICP',   name:'Internet Comp', emoji:'∞',  price:12.8,   chg24:-3.44, chg7:-8.4,  vol24:0.18,  mcap:5,    rsi:32, mtf:['down','down','down'],'signal':'strong_sell',score:18, sector:'Web3' },
  { rank:24, sym:'FIL',   name:'Filecoin',      emoji:'📁', price:5.84,   chg24:-1.24, chg7:-3.8,  vol24:0.14,  mcap:3.2,  rsi:38, mtf:['down','down','neu'],'signal':'sell',   score:30, sector:'Storage' },
  { rank:25, sym:'NEAR',  name:'NEAR Protocol', emoji:'Ⓝ',  price:4.82,   chg24:1.44,  chg7:5.2,   vol24:0.28,  mcap:4.8,  rsi:57, mtf:['up','neu','up'],   signal:'buy',        score:68, sector:'Layer1' },
];

/* ─── AI POTENTIAL DATA ─── */
const POTENTIAL_DATA = [
  { sym:'LINK', name:'Chainlink',   emoji:'⬡',  price:15.4,  signal:'strong_buy', overall:91,
    fundamental:82, technical:94, sentiment:88, onchain:90, macro:85,
    target7d:17.2,  target30d:22.4, target90d:32.0,
    downside:-12, confidence:88,
    catalysts:['Oracles cần thiết cho DeFi AI', 'Volume tăng 4 tuần liên tiếp', 'Tích hợp 20+ blockchain mới', 'Whale tích lũy 2.1M LINK'],
    risks:['Cạnh tranh từ Pyth Network', 'Phụ thuộc ETH ecosystem'],
    key_level_sup:14.8, key_level_res:18.0,
    summary:'LINK đang trong uptrend mạnh nhờ nhu cầu oracle bùng nổ từ AI + DeFi. Golden Cross trên 1D.'
  },
  { sym:'INJ',  name:'Injective',   emoji:'⚡', price:28.4,  signal:'strong_buy', overall:93,
    fundamental:90, technical:91, sentiment:94, onchain:95, macro:80,
    target7d:34.0,  target30d:45.0, target90d:68.0,
    downside:-15, confidence:86,
    catalysts:['TVL tăng 380% QoQ', 'DEX volume $1.2B/ngày', 'Midas RWA protocol launch', 'Venom partnership'],
    risks:['Thị trường DeFi còn non trẻ', 'Tokenomics inflation 2024'],
    key_level_sup:26.0, key_level_res:32.0,
    summary:'INJ là DeFi hub lớn nhất Cosmos. On-chain metrics bullish mạnh với volume DEX kỷ lục.'
  },
  { sym:'APT',  name:'Aptos',       emoji:'🅰',  price:11.2,  signal:'strong_buy', overall:89,
    fundamental:84, technical:88, sentiment:86, onchain:82, macro:78,
    target7d:13.5,  target30d:18.0, target90d:28.0,
    downside:-18, confidence:82,
    catalysts:['Daily active users tăng 45%', 'DeFi TVL $1.8B (+120%)', 'Microsoft AI partnership', 'Ecosystem fund $200M'],
    risks:['Vesting schedule áp lực bán', 'Competition từ SUI'],
    key_level_sup:10.5, key_level_res:13.0,
    summary:'Aptos hưởng lợi từ làn sóng Layer1 mới với TPS cao và Move language adoption tăng nhanh.'
  },
  { sym:'SUI',  name:'Sui',         emoji:'💧', price:4.12,  signal:'strong_buy', overall:88,
    fundamental:85, technical:86, sentiment:90, onchain:88, macro:76,
    target7d:4.9,   target30d:6.8,  target90d:10.5,
    downside:-20, confidence:80,
    catalysts:['Gaming ecosystem bùng nổ', 'zkLogin giúp mass adoption', 'Grayscale listing rumor', 'TVL $2.4B'],
    risks:['Token unlock tháng tới', 'Còn sớm trong chu kỳ'],
    key_level_sup:3.85, key_level_res:4.80,
    summary:'SUI có fundamentals mạnh nhất trong nhóm Move-based chains. DeFi và Gaming đều tăng trưởng tốt.'
  },
  { sym:'AVAX', name:'Avalanche',   emoji:'🔺', price:39.8,  signal:'strong_buy', overall:87,
    fundamental:88, technical:84, sentiment:82, onchain:86, macro:88,
    target7d:46.0,  target30d:62.0, target90d:85.0,
    downside:-14, confidence:84,
    catalysts:['Subnet tăng lên 100+', 'Evergreen Subnets ra mắt', 'BlackRock tokenization', 'Institutional adoption'],
    risks:['Gas fee cao hơn L2s', 'AVAX unlock schedule'],
    key_level_sup:37.5, key_level_res:44.0,
    summary:'AVAX được hưởng lợi lớn từ RWA tokenization trend và institutional blockchain adoption.'
  },
  { sym:'ARB',  name:'Arbitrum',    emoji:'🔵', price:0.892, signal:'buy',        overall:74,
    fundamental:80, technical:70, sentiment:76, onchain:72, macro:80,
    target7d:1.02,  target30d:1.35, target90d:2.10,
    downside:-22, confidence:72,
    catalysts:['TVL #1 L2 $18B', 'Orbit chains ecosystem', 'Gaming dApps explosion', 'DAO treasury active'],
    risks:['OP Stack cạnh tranh', 'Token unlock pressure'],
    key_level_sup:0.82, key_level_res:1.05,
    summary:'ARB dẫn đầu L2 về TVL nhưng đang consolidate. Breakout trên $1.05 xác nhận uptrend tiếp.'
  },
  { sym:'BTC',  name:'Bitcoin',     emoji:'₿',  price:108240, signal:'buy',       overall:82,
    fundamental:95, technical:82, sentiment:78, onchain:88, macro:86,
    target7d:115000,target30d:128000, target90d:148000,
    downside:-10, confidence:85,
    catalysts:['ETF net inflow $320M/ngày', 'Halving cycle Q4 2024', 'MicroStrategy mua thêm 15k BTC', 'Fed pivot signal'],
    risks:['RSI cận overbought', 'Macro uncertainty'],
    key_level_sup:104000, key_level_res:115000,
    summary:'BTC đang trong post-halving bull cycle. Institutional demand qua ETFs cực mạnh với inflow kỷ lục.'
  },
  { sym:'ETH',  name:'Ethereum',    emoji:'Ξ',  price:3890,   signal:'buy',       overall:77,
    fundamental:92, technical:76, sentiment:72, onchain:80, macro:84,
    target7d:4200,  target30d:5200, target90d:7500,
    downside:-14, confidence:78,
    catalysts:['ETH ETF approval incoming', 'Pectra upgrade roadmap', 'L2 ecosystem TVL $50B+', 'Deflationary since Merge'],
    risks:['Còn thấp hơn ATH 2021', 'ETH/BTC ratio giảm'],
    key_level_sup:3700, key_level_res:4400,
    summary:'ETH fundamentals rất mạnh với network revenue và deflationary model. ETF catalyst sắp tới.'
  },
  { sym:'UNI',  name:'Uniswap',     emoji:'🦄', price:9.84,   signal:'buy',       overall:72,
    fundamental:78, technical:70, sentiment:68, onchain:75, macro:75,
    target7d:11.2,  target30d:14.5, target90d:20.0,
    downside:-25, confidence:68,
    catalysts:['Uniswap v4 launch', 'Fee switch vote', 'UniswapX adoption', 'Protocol revenue ATH'],
    risks:['Regulatory uncertainty', 'DEX competition'],
    key_level_sup:9.20, key_level_res:11.50,
    summary:'UNI recovery mạnh sau SEC pressure giảm. V4 hooks sẽ mở ra revenue streams mới cho protocol.'
  },
  { sym:'SOL',  name:'Solana',      emoji:'◎',  price:168,    signal:'hold',      overall:55,
    fundamental:82, technical:48, sentiment:52, onchain:58, macro:80,
    target7d:172,   target30d:195, target90d:240,
    downside:-22, confidence:58,
    catalysts:['Meme coin ecosystem', 'Firedancer client sắp launch', 'DePIN growth', 'Jupiter DEX dominance'],
    risks:['Correction sau rally mạnh', 'Network downtime lịch sử'],
    key_level_sup:155, key_level_res:185,
    summary:'SOL đang consolidate sau rally từ $25. Cần breakout $185 để xác nhận uptrend tiếp tục.'
  },
  { sym:'DOT',  name:'Polkadot',    emoji:'●',  price:8.12,   signal:'sell',      overall:30,
    fundamental:60, technical:28, sentiment:32, onchain:30, macro:50,
    target7d:7.5,   target30d:6.8,  target90d:8.5,
    downside:-35, confidence:65,
    catalysts:['Parachain ecosystem', 'JAM upgrade'],
    risks:['Death cross trên 1D', 'Volume giảm liên tục', 'Ecosystem migration sang Polkadot 2.0'],
    key_level_sup:7.80, key_level_res:9.00,
    summary:'DOT trong downtrend rõ ràng với death cross và volume thấp. Chờ xác nhận đáy trước khi entry.'
  },
  { sym:'ICP',  name:'ICP',         emoji:'∞',  price:12.8,   signal:'sell',      overall:18,
    fundamental:40, technical:18, sentiment:20, onchain:15, macro:45,
    target7d:11.5,  target30d:10.2, target90d:9.0,
    downside:-42, confidence:72,
    catalysts:['DFINITY grants', 'AI compute potential'],
    risks:['Tokenomics rất xấu', 'Mint rate cao', 'Bearish momentum mạnh', 'Volume sụt giảm'],
    key_level_sup:12.0, key_level_res:14.5,
    summary:'ICP có tokenomics áp lực bán liên tục. Technical bearish mạnh. Tránh entry trong thời điểm này.'
  },
];

/* ─── MARKET HEALTH DATA ─── */
const FUNDING_DATA = [
  { sym:'BTC',  binance: 0.0142, bybit: 0.0138, okx: 0.0145 },
  { sym:'ETH',  binance: 0.0094, bybit: 0.0091, okx: 0.0098 },
  { sym:'SOL',  binance:-0.0012, bybit:-0.0018, okx: 0.0004 },
  { sym:'BNB',  binance: 0.0052, bybit: 0.0048, okx: 0.0055 },
  { sym:'AVAX', binance: 0.0224, bybit: 0.0218, okx: 0.0228 },
  { sym:'LINK', binance: 0.0312, bybit: 0.0298, okx: 0.0318 },
  { sym:'INJ',  binance: 0.0418, bybit: 0.0404, okx: 0.0424 },
  { sym:'APT',  binance: 0.0188, bybit: 0.0182, okx: 0.0192 },
];

const ONCHAIN_DATA = [
  { label:'Whale Flows (24h)',  val:'+$1.8B', trend:'+12%', up:true  },
  { label:'Exchange Outflow',   val:'-12,400 BTC', trend:'Bullish', up:true  },
  { label:'Active Addresses',   val:'1.24M',   trend:'+8.4%', up:true  },
  { label:'Stablecoin Supply',  val:'$184B',   trend:'+2.1%', up:true  },
  { label:'Miner Revenue',      val:'$48.2M',  trend:'+5.8%', up:true  },
  { label:'Open Interest',      val:'$42.8B',  trend:'+18%',  up:true  },
  { label:'Liquidations (24h)', val:'$284M',   trend:'Longs 68%', up:false },
  { label:'Long/Short Ratio',   val:'1.42',    trend:'Bullish', up:true  },
];

const MACRO_TILES_DATA = [
  { name:'Fed Rate',      val:'5.25–5.50%',  cls:'neutral' },
  { name:'US CPI',        val:'3.2%',         cls:'neutral' },
  { name:'DXY Index',     val:'104.2 ↘',      cls:'bullish' },
  { name:'Gold',          val:'$2,412 ↗',     cls:'bullish' },
  { name:'VIX',           val:'14.8 (Low)',    cls:'bullish' },
  { name:'10Y Treasury',  val:'4.48%',         cls:'neutral' },
  { name:'S&P 500',       val:'+1.2%',         cls:'bullish' },
  { name:'Oil (WTI)',     val:'$78.4',         cls:'neutral' },
];

const FG_HISTORY = [
  { day:'T2', val:64 }, { day:'T3', val:68 }, { day:'T4', val:71 },
  { day:'T5', val:69 }, { day:'T6', val:74 }, { day:'T7', val:76 },
  { day:'CN', val:72 },
];

/* ─── MARKET TABS LOGIC ─── */
document.querySelectorAll('.mkt-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.mkt-tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.mkt-pane').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    const pane = document.getElementById('mkt-' + btn.dataset.mkt);
    if (pane) pane.classList.add('active');

    // Lazy-render each pane
    if (btn.dataset.mkt === 'scanner')   renderScanner();
    if (btn.dataset.mkt === 'potential') renderPotential();
    if (btn.dataset.mkt === 'health')    renderMarketHealth();
    if (btn.dataset.mkt === 'heatmap')   renderHeatmap();
  });
});

/* ─── SCANNER ─── */
let scannerSort = { col: 'score', dir: 'desc' };
let scannerFilter = 'all';
let scannerSearch = '';
let scannerInitialized = false;

function signalLabel(s) {
  const m = { strong_buy:'Strong Buy', buy:'Buy', hold:'Hold', sell:'Sell', strong_sell:'Strong Sell' };
  return m[s] || s;
}

function scoreColor(n) {
  if (n >= 80) return 'var(--success)';
  if (n >= 60) return '#22d3ee';
  if (n >= 40) return 'var(--warning)';
  return 'var(--danger)';
}

function rsiClass(r) {
  if (r >= 70) return 'rsi-ob';
  if (r <= 30) return 'rsi-os';
  return 'rsi-neu';
}

function mtfDots(mtf) {
  const c = { up:'var(--success)', neu:'var(--warning)', down:'var(--danger)' };
  const l = ['1H', '4H', '1D'];
  return mtf.map((d, i) => `<span class="mtf-dot" style="background:${c[d]}" title="${l[i]}: ${d.toUpperCase()}"></span>`).join('');
}

function formatVol(n) { return n >= 10 ? n.toFixed(0) + 'B' : n.toFixed(2) + 'B'; }
function formatMcap(n) { return n >= 1000 ? (n/1000).toFixed(2) + 'T' : n.toFixed(0) + 'B'; }
function formatScanPrice(n) {
  if (n >= 1000) return '$' + n.toLocaleString('en-US', { maximumFractionDigits: 0 });
  if (n >= 1)    return '$' + n.toFixed(2);
  return '$' + n.toFixed(4);
}

function getFilteredScanner() {
  return SCANNER_DATA.filter(c => {
    const matchFilter = scannerFilter === 'all' || c.signal === scannerFilter;
    const matchSearch = !scannerSearch || c.sym.toLowerCase().includes(scannerSearch) || c.name.toLowerCase().includes(scannerSearch);
    return matchFilter && matchSearch;
  }).sort((a, b) => {
    const v = (x) => x[scannerSort.col] ?? 0;
    return scannerSort.dir === 'desc' ? v(b) - v(a) : v(a) - v(b);
  });
}

function renderScanner() {
  const tbody = document.getElementById('scanner-tbody');
  if (!tbody) return;

  const rows = getFilteredScanner();
  document.getElementById('scanner-footer').textContent = `Hiển thị ${rows.length} / ${SCANNER_DATA.length} coins`;

  tbody.innerHTML = rows.map(c => {
    const chg24Cls = c.chg24 >= 0 ? 'up' : 'down';
    const chg7Cls  = c.chg7  >= 0 ? 'up' : 'down';
    const scColor  = scoreColor(c.score);
    return `
      <tr>
        <td style="color:var(--muted)">#${c.rank}</td>
        <td>
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-size:16px">${c.emoji}</span>
            <div>
              <div style="font-weight:700">${c.sym}</div>
              <div style="font-size:10px;color:var(--muted)">${c.sector}</div>
            </div>
          </div>
        </td>
        <td style="font-weight:600">${formatScanPrice(c.price)}</td>
        <td class="${chg24Cls}">${c.chg24 > 0 ? '+' : ''}${c.chg24.toFixed(2)}%</td>
        <td class="${chg7Cls}">${c.chg7 > 0 ? '+' : ''}${c.chg7.toFixed(2)}%</td>
        <td style="color:var(--text-dim)">$${formatVol(c.vol24)}</td>
        <td style="color:var(--text-dim)">$${formatMcap(c.mcap)}</td>
        <td class="rsi-cell ${rsiClass(c.rsi)}">${c.rsi}</td>
        <td><div class="mtf-cell">${mtfDots(c.mtf)}</div></td>
        <td><span class="signal-badge ${c.signal}">${signalLabel(c.signal)}</span></td>
        <td>
          <div class="score-cell">
            <div class="score-bar-wrap"><div class="score-bar-fill" style="width:${c.score}%;background:${scColor}"></div></div>
            <span class="score-num" style="color:${scColor}">${c.score}</span>
          </div>
        </td>
        <td><button class="btn-analyze" onclick="openCoinDetail('${c.sym}')">Phân tích</button></td>
      </tr>`;
  }).join('');

  if (!scannerInitialized) {
    initScannerControls();
    scannerInitialized = true;
  }
}

function initScannerControls() {
  // Filter buttons
  document.querySelectorAll('.sf-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.sf-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      scannerFilter = btn.dataset.sf;
      renderScanner();
    });
  });

  // Search
  document.getElementById('scanner-search')?.addEventListener('input', (e) => {
    scannerSearch = e.target.value.toLowerCase();
    renderScanner();
  });

  // Sortable headers
  document.querySelectorAll('.scanner-table th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (scannerSort.col === col) {
        scannerSort.dir = scannerSort.dir === 'desc' ? 'asc' : 'desc';
      } else {
        scannerSort.col = col;
        scannerSort.dir = 'desc';
      }
      document.querySelectorAll('.scanner-table th').forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
      th.classList.add(scannerSort.dir === 'desc' ? 'sort-desc' : 'sort-asc');
      document.getElementById('scanner-sort-info').textContent = `Sắp xếp: ${col} ${scannerSort.dir === 'desc' ? '↓' : '↑'}`;
      renderScanner();
    });
  });
}

/* ─── AI POTENTIAL ─── */
let potentialFilter = 'all';
let potentialSort   = 'overall';
let potentialInitialized = false;

function ringPath(score, r = 15.9155) {
  const circ = 2 * Math.PI * r;
  const fill = (score / 100) * circ;
  return `${fill.toFixed(2)} ${(circ - fill).toFixed(2)}`;
}

function dimColor(v) {
  if (v >= 80) return 'var(--success)';
  if (v >= 60) return 'var(--primary)';
  if (v >= 40) return 'var(--warning)';
  return 'var(--danger)';
}

function renderPotential() {
  const grid = document.getElementById('potential-grid');
  if (!grid) return;

  const rows = POTENTIAL_DATA.filter(c =>
    potentialFilter === 'all' || c.signal === potentialFilter ||
    (potentialFilter === 'strong_buy' && c.signal === 'strong_buy') ||
    (potentialFilter === 'buy' && c.signal === 'buy') ||
    (potentialFilter === 'hold' && c.signal === 'hold')
  ).sort((a, b) => b[potentialSort] - a[potentialSort]);

  grid.innerHTML = rows.map(c => {
    const sc  = c.overall;
    const sc2 = dimColor(sc);
    const ringSVG = (v, col) => `
      <svg class="score-ring-svg" viewBox="0 0 36 36">
        <path class="ring-bg"   d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"/>
        <path class="ring-fill" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              style="stroke:${col};stroke-dasharray:${ringPath(v)}" />
        <text x="18" y="21" text-anchor="middle" fill="${col}" font-size="9" font-weight="700">${v}</text>
      </svg>`;

    const targetFmt = (t) => typeof t === 'number' && t > 100 ? '$' + t.toLocaleString('en-US', {maximumFractionDigits:0}) : '$' + t.toFixed(3).replace(/\.?0+$/, '');

    return `
      <div class="potential-card glass ${c.signal}" onclick="openPotentialDetail('${c.sym}')">
        <div class="pc-header">
          <div class="pc-icon">${c.emoji}</div>
          <div class="pc-info">
            <div class="pc-name">${c.sym} <span style="font-size:12px;font-weight:400;color:var(--text-dim)">${c.name}</span></div>
            <div class="pc-price">${formatScanPrice(c.price)}</div>
          </div>
          <div style="text-align:center">
            ${ringSVG(sc, sc2)}
            <div style="font-size:10px;color:var(--muted);margin-top:2px">Overall</div>
          </div>
        </div>

        <span class="signal-badge ${c.signal}" style="width:fit-content">${signalLabel(c.signal)}</span>

        <div class="pc-dims">
          ${[['Fundamental', c.fundamental], ['Technical', c.technical], ['Sentiment', c.sentiment], ['On-Chain', c.onchain]].map(([l, v]) => `
            <div class="dim-row">
              <span class="dim-label">${l}</span>
              <div class="dim-bar"><div class="dim-fill" style="width:${v}%;background:${dimColor(v)}"></div></div>
              <span class="dim-val" style="color:${dimColor(v)}">${v}</span>
            </div>`).join('')}
        </div>

        <div class="pc-targets">
          <div style="font-size:10px;color:var(--muted);margin-bottom:6px">Mục tiêu giá</div>
          <div class="targets-row">
            <div class="tgt-item">
              <div class="tgt-label">7 ngày</div>
              <div class="tgt-price up">${targetFmt(c.target7d)}</div>
            </div>
            <div class="tgt-item">
              <div class="tgt-label">Hiện tại</div>
              <div class="tgt-price">${formatScanPrice(c.price)}</div>
            </div>
            <div class="tgt-item">
              <div class="tgt-label">30 ngày</div>
              <div class="tgt-price up">${targetFmt(c.target30d)}</div>
            </div>
            <div class="tgt-item">
              <div class="tgt-label">90 ngày</div>
              <div class="tgt-price up">${targetFmt(c.target90d)}</div>
            </div>
          </div>
        </div>

        <div class="pc-catalysts">
          ${c.catalysts.slice(0,3).map(cat => `<span class="catalyst-tag">${cat}</span>`).join('')}
        </div>

        <div style="font-size:11px;color:var(--text-dim);line-height:1.55">${c.summary}</div>
      </div>`;
  }).join('');

  if (!potentialInitialized) {
    document.querySelectorAll('.pf-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.pf-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        potentialFilter = btn.dataset.pf;
        renderPotential();
      });
    });
    document.getElementById('potential-sort')?.addEventListener('change', (e) => {
      potentialSort = e.target.value;
      renderPotential();
    });
    potentialInitialized = true;
  }
}

/* ─── MARKET HEALTH ─── */
let healthInitialized = false;

function drawFearGreedGauge(val) {
  const canvas = document.getElementById('fg-gauge');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  const cx = W / 2, cy = H - 10, r = H - 20;
  const startAngle = Math.PI;
  const endAngle   = 0;

  // Background arc
  ctx.beginPath();
  ctx.arc(cx, cy, r, startAngle, endAngle);
  ctx.lineWidth = 18;

  const grad = ctx.createLinearGradient(cx - r, 0, cx + r, 0);
  grad.addColorStop(0,   '#EF4444');
  grad.addColorStop(0.25,'#F59E0B');
  grad.addColorStop(0.5, '#EAB308');
  grad.addColorStop(0.75,'#22C55E');
  grad.addColorStop(1,   '#16A34A');
  ctx.strokeStyle = grad;
  ctx.stroke();

  // Needle
  const angle = startAngle + (val / 100) * Math.PI;
  const nLen = r - 10;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(
    cx + nLen * Math.cos(angle),
    cy + nLen * Math.sin(angle)
  );
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 2.5;
  ctx.lineCap = 'round';
  ctx.stroke();

  // Center dot
  ctx.beginPath();
  ctx.arc(cx, cy, 5, 0, Math.PI * 2);
  ctx.fillStyle = '#fff';
  ctx.fill();

  // Labels
  ctx.font = '10px sans-serif';
  ctx.fillStyle = 'rgba(255,255,255,0.5)';
  ctx.textAlign = 'left';  ctx.fillText('Sợ',  8,  cy - 2);
  ctx.textAlign = 'right'; ctx.fillText('Tham', W - 8, cy - 2);
}

function renderMarketHealth() {
  if (healthInitialized) return;
  healthInitialized = true;

  // Fear & Greed gauge
  const fgVal = 72;
  drawFearGreedGauge(fgVal);

  // F&G history bars
  const hist = document.getElementById('fg-history');
  if (hist) {
    hist.innerHTML = FG_HISTORY.map(d => {
      const h = Math.round(d.val * 0.45);
      const col = d.val >= 60 ? 'var(--success)' : d.val >= 40 ? 'var(--warning)' : 'var(--danger)';
      return `<div class="fg-day">
        <div class="fg-day-bar" style="height:${h}px;background:${col};opacity:0.8"></div>
        <div class="fg-day-lbl">${d.day}</div>
      </div>`;
    }).join('');
  }

  // BTC dominance mini chart
  const domCanvas = document.getElementById('dom-chart');
  if (domCanvas) {
    const ctx = domCanvas.getContext('2d');
    const domHistory = [49.2, 50.1, 51.4, 51.8, 52.0, 51.6, 52.4];
    const w = domCanvas.width || domCanvas.parentElement.clientWidth;
    const h = 60;
    domCanvas.width = w; domCanvas.height = h;
    const min = Math.min(...domHistory) - 1, max = Math.max(...domHistory) + 1;
    ctx.beginPath();
    domHistory.forEach((v, i) => {
      const x = (i / (domHistory.length - 1)) * w;
      const y = h - ((v - min) / (max - min)) * (h - 4) - 2;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.strokeStyle = 'var(--primary)';
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  // Funding rates table
  const fundingTbody = document.getElementById('funding-tbody');
  if (fundingTbody) {
    fundingTbody.innerHTML = FUNDING_DATA.map(f => {
      const fmt = (v) => `<span class="${v > 0.01 ? 'funding-pos' : v < -0.005 ? 'funding-neg' : 'funding-neu'}">${v > 0 ? '+' : ''}${(v * 100).toFixed(4)}%</span>`;
      const avg = (f.binance + f.bybit + f.okx) / 3;
      const status = avg > 0.015 ? '<span class="signal-badge buy" style="font-size:10px">Bullish</span>'
                   : avg < 0 ? '<span class="signal-badge sell" style="font-size:10px">Bearish</span>'
                   : '<span class="signal-badge hold" style="font-size:10px">Neutral</span>';
      return `<tr>
        <td><strong>${f.sym}</strong></td>
        <td>${fmt(f.binance)}</td>
        <td>${fmt(f.bybit)}</td>
        <td>${fmt(f.okx)}</td>
        <td>${status}</td>
      </tr>`;
    }).join('');
  }

  // On-chain grid
  const ocGrid = document.getElementById('onchain-grid');
  if (ocGrid) {
    ocGrid.innerHTML = ONCHAIN_DATA.map(d => `
      <div class="onchain-item">
        <div class="oc-label">${d.label}</div>
        <div class="oc-val ${d.up ? 'up' : 'down'}">${d.val}</div>
        <div class="oc-trend" style="color:${d.up ? 'var(--success)' : 'var(--danger)'}">${d.trend}</div>
      </div>`).join('');
  }

  // Macro tiles (try API first)
  const macroEl = document.getElementById('macro-tiles');
  if (macroEl) {
    const renderMacroTiles = (data) => {
      macroEl.innerHTML = data.map(t => `
        <div class="macro-tile ${escapeHtml(t.cls)}">
          <div class="mt-name">${escapeHtml(t.name)}</div>
          <div class="mt-val">${escapeHtml(String(t.val))}</div>
        </div>`).join('');
    };
    renderMacroTiles(MACRO_TILES_DATA);

    apiJson('/api/macro').then(d => {
      if (!d || typeof d !== 'object') return;
      const tiles = Object.entries(d).slice(0, 8).map(([k, v]) => ({
        name: k.replace(/_/g, ' '),
        val: typeof v === 'number' ? v.toFixed(2) : String(v),
        cls: 'neutral',
      }));
      if (tiles.length) renderMacroTiles(tiles);
    }).catch(() => {});
  }
}

/* ─── COIN DETAIL MODAL ─── */
window.openCoinDetail = function (sym) {
  const coin = SCANNER_DATA.find(c => c.sym === sym);
  const pot  = POTENTIAL_DATA.find(c => c.sym === sym);
  if (!coin) return;

  const chgClass = coin.chg24 >= 0 ? 'up' : 'down';
  const supportLevels = pot ? [
    { type:'Support',    price: formatScanPrice(pot.key_level_sup), strength:'Mạnh' },
    { type:'Current',    price: formatScanPrice(coin.price),         strength:'—'    },
    { type:'Resistance', price: formatScanPrice(pot.key_level_res), strength:'Mạnh' },
  ] : [];

  const analysisRows = [
    ['EMA Cross',        coin.mtf[2] === 'up' ? 88 : 32, coin.mtf[2] === 'up'],
    ['Volume',           Math.min(95, coin.vol24 * 3 + 40), coin.vol24 > 2],
    ['RSI (14)',         coin.rsi, coin.rsi >= 50 && coin.rsi < 70],
    ['Trend Strength',   coin.score, coin.score >= 60],
    ['Market Cap Rank',  Math.max(10, 100 - coin.rank * 3), coin.rank <= 10],
    ['Sector Momentum',  coin.chg7 >= 0 ? 68 : 35, coin.chg7 >= 0],
  ];

  document.getElementById('pos-modal-title').textContent = `${coin.sym} — Phân tích toàn diện`;
  document.getElementById('pos-modal-body').innerHTML = `
    <div class="detail-header">
      <span class="detail-coin-icon">${coin.emoji}</span>
      <div class="detail-meta">
        <h3>${coin.name} (${coin.sym})</h3>
        <p>${formatScanPrice(coin.price)} &nbsp; <span class="${chgClass}">${coin.chg24 > 0 ? '+' : ''}${coin.chg24.toFixed(2)}% (24h)</span> &nbsp;·&nbsp; Rank #${coin.rank}</p>
      </div>
      <span class="signal-badge ${coin.signal}" style="align-self:flex-start">${signalLabel(coin.signal)}</span>
    </div>

    <div class="detail-grid">
      <div class="detail-section">
        <h4>Phân tích kỹ thuật</h4>
        ${analysisRows.map(([l, v, up]) => `
          <div class="analysis-bar-row">
            <span class="analysis-bar-label">${l}</span>
            <div class="analysis-bar-outer"><div class="analysis-bar-inner" style="width:${v}%;background:${up ? 'var(--success)' : 'var(--danger)'}"></div></div>
            <span class="analysis-bar-val" style="color:${up ? 'var(--success)' : 'var(--danger)'}">${Math.round(v)}</span>
          </div>`).join('')}
      </div>

      <div class="detail-section">
        <h4>Tín hiệu đa timeframe</h4>
        <div class="tf-signal-grid">
          ${['1H','4H','1D'].map((tf, i) => {
            const s = coin.mtf[i];
            const col = s === 'up' ? 'var(--success)' : s === 'down' ? 'var(--danger)' : 'var(--warning)';
            return `<div class="tf-signal-item">
              <div class="tf-signal-name">${tf}</div>
              <div class="tf-signal-val" style="color:${col}">${s.toUpperCase()}</div>
            </div>`;
          }).join('')}
          <div class="tf-signal-item">
            <div class="tf-signal-name">RSI</div>
            <div class="tf-signal-val ${rsiClass(coin.rsi)}">${coin.rsi}</div>
          </div>
          <div class="tf-signal-item">
            <div class="tf-signal-name">Score</div>
            <div class="tf-signal-val" style="color:${scoreColor(coin.score)}">${coin.score}/100</div>
          </div>
          <div class="tf-signal-item">
            <div class="tf-signal-name">7d</div>
            <div class="tf-signal-val ${coin.chg7 >= 0 ? 'up' : 'down'}">${coin.chg7 > 0 ? '+' : ''}${coin.chg7.toFixed(1)}%</div>
          </div>
        </div>

        ${supportLevels.length ? `
        <h4 style="margin-top:14px">Vùng Key Levels</h4>
        <div class="support-levels">
          ${supportLevels.map(l => `
            <div class="level-row">
              <span class="level-type">${l.type}</span>
              <span class="level-price">${l.price}</span>
              <span class="level-strength">${l.strength}</span>
            </div>`).join('')}
        </div>` : ''}
      </div>
    </div>

    ${pot ? `
    <div class="detail-section" style="margin-top:14px">
      <h4>AI Đánh giá tiềm năng</h4>
      <p style="font-size:13px;color:var(--text-dim);line-height:1.6;margin-bottom:10px">${pot.summary}</p>
      <div style="display:flex;flex-wrap:wrap;gap:6px">
        ${pot.catalysts.map(c2 => `<span class="catalyst-tag">✓ ${escapeHtml(c2)}</span>`).join('')}
      </div>
      ${pot.risks.length ? `<div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px">
        ${pot.risks.map(r => `<span class="catalyst-tag" style="border-color:rgba(239,68,68,0.3);color:var(--danger);background:rgba(239,68,68,0.08)">⚠ ${escapeHtml(r)}</span>`).join('')}
      </div>` : ''}
    </div>` : ''}
  `;

  document.getElementById('pos-modal').style.display = 'flex';
};

window.openPotentialDetail = function (sym) {
  window.openCoinDetail(sym);
};

/* ─── REFRESH MARKET DATA ─── */
function liveUpdateScanner() {
  SCANNER_DATA.forEach(c => {
    const noise = (Math.random() - 0.495) * 0.08;
    c.price = Math.max(0.001, c.price * (1 + noise));
    c.chg24 = +(c.chg24 + (Math.random() - 0.5) * 0.05).toFixed(2);
  });
  const tbody = document.getElementById('scanner-tbody');
  if (tbody && tbody.children.length) renderScanner();
}

// Update scanner prices every 4 seconds when visible
setInterval(liveUpdateScanner, 4000);

async function loadMarketMeta() {
  try {
    const macro = await apiJson('/api/macro');
    // Update meta chips if server provides relevant data
    if (macro && typeof macro === 'object') {
      const vix = macro.vix ?? macro['VIX'];
      if (vix) document.getElementById('btc-dom').textContent = '52.4%';
    }
  } catch { /* use defaults */ }
}

/* ─── INIT ─── */
(function init() {
  initMainChart();
  loadPortfolio();
  addWelcomeMessage();
})();
