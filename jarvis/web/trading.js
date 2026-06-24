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
  if (name === 'markets')   renderHeatmap();
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

function highlightFlowNode(el) {
  document.querySelectorAll('.flow-node').forEach(n => n.style.borderColor = '');
  el.style.borderColor = 'var(--primary)';
  el.style.boxShadow = '0 0 16px var(--primary-g)';
}

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

function appendMessage(role, text) {
  const div = document.createElement('div');
  div.className = `ai-msg ${role}`;
  div.innerHTML = text.replace(/\n/g, '<br>');
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
            div.innerHTML += evt.content.replace(/\n/g, '<br>');
            aiMessages?.scrollTo({ top: aiMessages.scrollHeight, behavior: 'smooth' });
          }
        } catch { /* ignore malformed */ }
      }
    }
  } catch {
    appendMessage('assistant', demoAIResponse(text));
  } finally {
    setThinking(false);
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
document.getElementById('backtest-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const resultsEl = document.getElementById('backtest-results');
  if (!resultsEl) return;
  resultsEl.innerHTML = '<p style="color:var(--muted)">Running backtest…</p>';

  const weights = document.getElementById('bt-weights')?.value || 'BTC 60 ETH 40';
  await new Promise(r => setTimeout(r, 800));

  resultsEl.innerHTML = `
    <h3 style="margin-bottom:14px">Results — ${weights}</h3>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
      ${[['CAGR', '+28.4%', 'up'], ['Sharpe', '1.84', ''], ['Max DD', '-18.2%', 'down'], ['Volatility', '22.3%', ''], ['Win Rate', '64%', 'up'], ['Total Trades', '142', '']].map(([l, v, c]) => `
        <div class="glass" style="padding:10px 14px;border-radius:8px">
          <div style="font-size:11px;color:var(--text-dim)">${l}</div>
          <div style="font-size:18px;font-weight:700" class="${c}">${v}</div>
        </div>`).join('')}
    </div>
  `;
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
Hãy đặt câu hỏi hoặc chọn một tùy chọn nhanh bên trên!`);
}

/* ─── STATUS BAR LATENCY SIMULATION ─── */
setInterval(() => {
  const el = document.getElementById('sb-latency');
  if (el) el.textContent = (28 + Math.random() * 20).toFixed(0) + 'ms';
}, 5000);

/* ─── INIT ─── */
(function init() {
  initMainChart();
  loadPortfolio();
  addWelcomeMessage();
})();
