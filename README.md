# JARVIS — AI Investment Agent

An autonomous investment agent powered by Claude that thinks like a top-tier
venture capitalist applied to public markets: thesis-driven, power-law-aware,
macro-conscious, and risk-disciplined.

```
┌─────────────────────────────────────────────────────────────┐
│                     InvestmentAgent (Claude)                │
│   VC-mindset system prompt · adaptive thinking · web search │
└──────┬──────────┬───────────┬───────────┬──────────┬────────┘
       │          │           │           │          │
   market data  macro     journal     portfolio   place_order
   (yfinance)  snapshot  (theses +    (mark-to-      │
                          lessons)     market)       ▼
                                              ┌──────────────┐
                                              │ RiskManager  │  hard limits
                                              └──────┬───────┘
                                                     ▼
                                              human approval (optional)
                                                     ▼
                                       PaperBroker │ AlpacaBroker
```

## What it does

- **Analyzes economic trends** — reads the macro regime from live market
  proxies (yield curve, VIX, credit spreads, dollar, commodities) and
  searches the web for breaking news, earnings, and catalysts.
- **Plans like a VC** — every position rests on a written thesis with an
  explicit invalidation condition and a conviction level, persisted to a
  journal the agent re-reads across sessions. It records lessons from wins
  and losses and compounds them.
- **Automates investing safely** — trades execute through an independent
  risk manager (position-size caps, cash-reserve floor, daily trade limits)
  that the model cannot override, with optional human approval per order.
  **Paper trading is the default**; live execution is an explicit opt-in.

## Quick start

```bash
git clone <this repo> && cd Ai-agent-1.0
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then put your ANTHROPIC_API_KEY in .env
```

### Commands

```bash
python -m jarvis dashboard                  # web dashboard at http://127.0.0.1:8000
python -m jarvis chat                       # interactive terminal session
python -m jarvis analyze NVDA               # VC-style deep-dive on one ticker
python -m jarvis briefing                   # daily macro + portfolio briefing
python -m jarvis auto --once                # one autonomous management cycle
python -m jarvis auto                       # autonomous loop (daily by default)
python -m jarvis backtest "NVDA=0.4,GLD=0.2"  # backtest an allocation vs SPY
python -m jarvis strategy NVDA --type sma_cross --stop-loss 8   # strategy backtest
python -m jarvis optimize NVDA --type sma_cross   # grid-search strategy params
python -m jarvis models                     # list / pull / select local models
python -m jarvis telegram                   # control the agent from Telegram
python -m jarvis portfolio                  # print holdings (no LLM call)
```

## Telegram bot

`python -m jarvis telegram` lets you run the whole agent from your phone:

- Send any message to chat (e.g. *"analyze NVDA"*) — replies stream in and
  edit live; `/portfolio`, `/briefing`, `/reset`, `/help` commands too.
- **Order approval by inline button** — when the agent wants to trade, you
  get an Approve / Deny message; nothing executes until you tap (5-min
  timeout = deny), exactly like the web modal.
- **Alert push** — drawdown/stop alerts arrive in the chat as well.

Set `TELEGRAM_BOT_TOKEN` (from [@BotFather](https://t.me/BotFather)); on first
`/start` the bot prints your chat id — put it in `TELEGRAM_CHAT_ID` to lock
the bot to you. The bot reuses the same persisted conversation, journal, and
risk gate as the CLI and dashboard.

## Crypto / multi-exchange (CCXT)

Crypto symbols (`BTC-USD`, `ETH-USD`, …) already work in paper mode through
the normal data path. For **live crypto execution** on 100+ exchanges, set
`EXECUTION_MODE=crypto` and install CCXT (`pip install ccxt`):

```bash
EXECUTION_MODE=crypto CCXT_EXCHANGE=binance CCXT_API_KEY=... CCXT_SECRET=...
```

The broker maps yfinance-style tickers to exchange pairs (`BTC-USD` →
`BTC/USDT`, configurable via `CCXT_QUOTE`), so quotes, the risk gate, and
protective stops all keep working. It **defaults to the exchange sandbox**
(`CCXT_SANDBOX=true`) — set it false only when you mean to trade real funds,
and the autonomous loop still refuses unattended real-money trading without
`AUTO_APPROVE=true`.

## Quant features (Freqtrade-style)

JARVIS now carries a technical-trading layer alongside its LLM reasoning:

- **Technical indicators** — RSI, MACD, Bollinger Bands, 50/200-day SMAs and
  ATR, with a plain-language signal read. The agent calls `get_indicators`
  to time entries/exits; also at `GET /api/indicators?symbol=NVDA`.
- **Protective orders** — attach a **stop-loss**, **trailing stop**, and/or
  **take-profit** to any position. A monitor checks them on every dashboard
  alert poll and every autonomous cycle and **auto-exits** the full position
  when one triggers (a protective sell needs no approval). Set them in chat
  ("put an 8% stop and a 15% trailing stop on NVDA") or the agent does it
  itself after opening a position; they show on the Overview tab.
- **Strategy backtester** — rule-based timing strategies (`sma_cross`, `rsi`,
  `macd_cross`, `bollinger`) backtested on one ticker with fees and an
  optional stop-loss, reporting win rate, number of trades, CAGR/Sharpe/
  drawdown, and the comparison vs buy-and-hold. Use the **Strategy Backtest**
  card on the Backtest tab, the CLI (`jarvis strategy`), or the agent's
  `backtest_strategy` tool.
- **Parameter optimization (Hyperopt-lite)** — grid-search a strategy's
  parameters over history and rank them by Sharpe / return / CAGR, returning
  the best settings and a leaderboard. **Optimize Parameters** card on the
  Backtest tab, `jarvis optimize`, or the `optimize_strategy` tool.
- **Resting orders — limit, stop, and OCO** — queue an entry/exit at a target
  price instead of trading at market: limit buy (buy the dip), limit sell
  (take profit), stop buy (breakout), stop sell (breakdown). Bracket a long
  with a **one-cancels-other** take-profit + stop-loss pair. A monitor fills
  triggered orders on every alert poll and autonomous cycle (re-validating
  buys against the risk gate). Shown on the Overview tab; set them in chat or
  via the `place_limit_order` / `place_oco_order` tools.
- **Time-based ROI table (Freqtrade `minimal_roi`)** — set `ROI_TABLE` to a
  `{held_days: min_profit}` map (e.g. take +10% any time, +5% after 5 days,
  any profit after 60) and the monitor auto-takes-profit on every position
  once it reaches the age-appropriate target — no per-position setup needed.
- **Random search** — the optimizer runs grid *or* random search
  (`--method random`), sampling large parameter spaces with a seed for
  reproducibility.

The Overview tab also breaks exposure down by **sector, geography (country of
domicile), and asset class** (equity / ETF / crypto), not just per-symbol.

## Choosing the AI model (cloud or local)

JARVIS runs on either **Claude (cloud)** or a **local open-weight model**:

| | Cloud — Anthropic Claude (default) | Local — Ollama |
|---|---|---|
| Setup | `ANTHROPIC_API_KEY` | install [Ollama](https://ollama.com), `ollama serve` |
| Cost | per-token API billing | free |
| Privacy | prompts leave your machine | fully on-device |
| Web search | ✅ live, with citations | ❌ (no server-side search) |
| Quality | highest | depends on model/hardware |

Manage local models from the **Models** tab in the dashboard (download with a
live progress bar, then click *Use*), or from the CLI:

```bash
python -m jarvis models                 # show installed + suggested models
python -m jarvis models pull qwen2.5:7b # download a tool-calling model
python -m jarvis models use qwen2.5:7b  # switch the agent to it (persists)
python -m jarvis models use anthropic:claude-opus-4-8   # switch back to cloud
```

The selection is saved to `data/llm_selection.json`, so it survives restarts.
Local models keep every tool (market data, portfolio, backtest, journal,
risk-gated trading) — they only lose Anthropic's server-side web search.
Pick a model that supports tool/function calling (the suggested list does).

### Docker

```bash
cp .env.example .env                # set ANTHROPIC_API_KEY (+ a dashboard token)
docker compose up -d                # dashboard on 127.0.0.1:8000
docker compose --profile auto up -d # also run the autonomous daily cycle
```

State persists in the `jarvis-data` volume.

## Web dashboard

`python -m jarvis dashboard` serves a dark-themed single-page app:

- **Overview** — KPI cards (equity, cash, invested, unrealized P&L, daily
  trade budget), an **equity curve vs the S&P 500** (both indexed to 100),
  an **allocation donut** plus a **sector-exposure donut**, live **macro
  regime tiles** (yield curve with an inversion signal, VIX, credit, dollar,
  oil, gold, bitcoin), recent alerts, positions marked to market, and the
  active risk limits.
- **Chat** — talk to the agent in the browser with streamed responses and
  tool-call indicators, one-click quick actions (daily briefing, portfolio
  review, "find an asymmetric bet"), and a **persistent conversation** that
  survives restarts (reset anytime with "New conversation").
- **Backtest** — enter a target-weight allocation (e.g. `NVDA=0.4, GLD=0.2`,
  remainder = cash), pick a period and rebalance cadence, and get CAGR,
  volatility, Sharpe, max drawdown, and excess return vs a benchmark with
  the simulated curve. The agent has the same tool and is instructed to
  backtest allocations before proposing them.
- **Models** — switch between cloud Claude and local Ollama models, see
  what's installed, and download a new local model with a live progress bar.
- **Order approvals in the browser** — when the agent wants to trade, a
  modal shows the order, conviction, and rationale; nothing executes until
  you click Approve (denials and 5-minute timeouts both cancel the order).
- **Alerts** — a banner appears when a holding falls past its drawdown
  threshold, equity draws down from its peak, or equity moves sharply in a
  day. Each alert also fans out (once per day per rule) to an optional
  **webhook** (Slack/Discord-style) and **SMTP email**.
- **Journal** — every recorded thesis (with conviction badge, horizon, and
  invalidation condition) and lessons learned.
- **Trades** — the full ledger with per-trade rationales and fees.

The equity curve builds up day over day: each dashboard load snapshots
total equity alongside the S&P 500 close into `data/equity_history.json`.

### Three dashboard skins

A view switcher in the header flips between three presentations of the same
live data (pick by taste — they share the API and your token):

- **Classic** (`/`) — the full control surface: chat, charts, backtest,
  optimize, models, journal, trades, approvals.
- **Quant Research** (`/quant`) — a dense Bloomberg-style terminal:
  risk-metric strip (ann. return/vol, Sharpe, Sortino, max DD, VaR/CVaR),
  a **correlation heatmap** of your holdings, concentration stats (HHI,
  effective N), an **underwater drawdown** chart, a **daily-return
  histogram**, and ranked sector/geography/asset-class exposure bars.
- **Glassmorphism AI** (`/glass`) — a frosted-glass UI with an animated
  aurora background: glowing KPI tiles, equity-vs-S&P curve, allocation
  donut, macro tiles, and a built-in streaming **AI chat** panel.

The Quant view is backed by a new `GET /api/quant` endpoint (correlation,
risk, concentration); the Glass view reuses the existing endpoints.

> **Auth:** set `JARVIS_DASHBOARD_TOKEN` and every API request must carry
> `Authorization: Bearer <token>` — the UI prompts for it once and stores it
> locally. The token is **required** before exposing the dashboard beyond
> `127.0.0.1`, since the dashboard can approve trades.

Example session:

```
you > What's the macro setup right now, and is there an asymmetric bet in semis?

jarvis > [pulls macro snapshot, searches recent news, checks quotes...]
The regime is cautiously risk-on: the 10Y/3M curve has re-steepened to ...
```

## Architecture

| Module | Role |
|---|---|
| `jarvis/agent.py` | Agentic loop: Claude (Opus 4.8, adaptive thinking) + tool dispatch, streaming output, `pause_turn`/`refusal` handling |
| `jarvis/prompts.py` | VC-doctrine system prompt and task prompts (analyze / briefing / auto-cycle) |
| `jarvis/tools/market_data.py` | Quotes, price history with vol/drawdown/SMAs, fundamentals (yfinance, no API key) |
| `jarvis/tools/macro.py` | Macro regime snapshot from liquid market proxies + yield-curve spread |
| `jarvis/memory.py` | Persistent journal: investment theses (with invalidation conditions) and lessons |
| `jarvis/portfolio.py` | Local ledger: cash, positions, trade history, mark-to-market (JSON on disk) |
| `jarvis/risk.py` | Hard order gate: per-order cap, concentration cap, cash floor, daily limit |
| `jarvis/brokers/` | `PaperBroker` (default; slippage + commission), `AlpacaBroker` (equities), `CCXTBroker` (crypto, 100+ exchanges) |
| `jarvis/telegram_bot.py` | Telegram long-poll bot: chat, commands, inline-button order approval |
| `jarvis/backtest.py` | Target-weight backtester: rebalancing, trading costs, CAGR/Sharpe/drawdown vs benchmark |
| `jarvis/alerts.py` | Alert rules (position/portfolio drawdown, daily move) + webhook/email fan-out, deduped daily |
| `jarvis/history.py` | Daily equity-curve snapshots with S&P 500 benchmark, normalized for charting |
| `jarvis/tools/indicators.py` | Technical indicators in pure pandas (RSI, MACD, Bollinger, SMA/EMA, ATR) |
| `jarvis/strategy.py` | Signal-level strategy backtester (sma_cross/rsi/macd/bollinger) with fees + stop-loss |
| `jarvis/stops.py` | Protective orders (stop-loss/trailing/take-profit) + auto-exit engine |
| `jarvis/orders.py` | Resting limit/stop/OCO orders + trigger-fill engine (risk-revalidated) |
| `jarvis/optimize.py` | Strategy parameter grid/random search (Hyperopt-lite), ranked by objective |
| `jarvis/tools/quant.py` | Quant analytics: correlation matrix, risk metrics, concentration (HHI) |
| `jarvis/toolkit.py` | Shared tool implementations + dual schema formats (Anthropic & OpenAI/Ollama) |
| `jarvis/llm/ollama.py` | Local-model client: health, list, pull (streamed progress), chat |
| `jarvis/server.py` | FastAPI backend: REST + SSE chat/pull streaming + browser order-approval hub + Bearer-token auth |
| `jarvis/web/` | Three dashboards (Classic SPA, Quant terminal, Glassmorphism AI) — vanilla JS + Chart.js, no build step |
| `jarvis/cli.py` | CLI, interactive order approval, autonomous scheduler, backtest, dashboard launcher |

Design choices worth knowing:

- **Manual agentic loop** (not the SDK tool runner) so order placement can be
  intercepted for risk validation and human approval before execution.
- **The risk manager is code, not prompt.** The model is told the limits, but
  enforcement happens in `risk.py` regardless of what the model argues.
- **State lives on disk** (`data/`): portfolio, theses, lessons. The
  autonomous loop builds a fresh agent each cycle and re-reads state, so
  context stays small and nothing depends on a long-lived process.
- **Web search is server-side** (Anthropic's `web_search` tool), so the agent
  gets current news with citations and no news-API key is needed.

## Safety model

1. `EXECUTION_MODE=paper` by default — simulated fills, real prices.
2. Every order passes `RiskManager.validate()`; rejections return the reason
   to the model, which must adapt rather than retry.
3. In `chat` mode each order requires interactive y/n approval unless
   `AUTO_APPROVE=true`.
4. The autonomous loop refuses to run in live mode unless `AUTO_APPROVE=true`
   is set explicitly.
5. Live mode routes to Alpaca and defaults to Alpaca's **paper** endpoint;
   you must deliberately point `ALPACA_BASE_URL` at the production API.

## Configuration

All knobs live in `.env` (see `.env.example`): model and effort level,
execution mode, starting cash, risk limits, and Alpaca credentials.

## Tests

The portfolio and risk layers are dependency-free and tested offline:

```bash
pip install pytest
pytest
```

## How JARVIS compares to Freqtrade

[Freqtrade](https://www.freqtrade.io) is a mature open-source **crypto
algo-trading bot**. It and JARVIS solve different problems — Freqtrade
executes precise, backtested rule-based strategies at high frequency;
JARVIS is an LLM analyst that reasons about theses and macro and trades
discretionarily with a human in the loop. What Freqtrade has that JARVIS
does **not** yet (an honest gap list, roughly by impact):

| Area | Freqtrade | JARVIS today | Gap |
|---|---|---|---|
| **Live exchange execution** | Many crypto exchanges via CCXT | Alpaca (equities) + CCXT (crypto, 100+ exchanges) ✅ | Comparable |
| **Technical indicators** | Full TA-Lib / pandas-ta library | RSI, MACD, Bollinger, SMA/EMA, ATR ✅ | Smaller library |
| **Order types** | Limit, stop-loss, trailing stop, OCO | Market + stop-loss/trailing/take-profit + limit/stop/OCO ✅ | Comparable |
| **Strategy optimization** | Hyperopt (Bayesian param search) | Grid-search over params, ranked ✅ | Grid, not Bayesian |
| **Strategy backtesting** | Tick/candle-level, per-trade | Signal-level + allocation-level ✅ | Not tick-level |
| **Live price feed** | Websocket streaming | Polled quotes (60s cache) | No real-time stream |
| **Dry-run vs live parity** | Same engine both modes | Separate paper/live brokers | Less battle-tested live path |
| **Position management** | Per-trade stop-loss/ROI/timeouts | Auto stop-loss/trailing/take-profit + time-based ROI table ✅ | Comparable |
| **Strategy optimization (search)** | Bayesian (Hyperopt) | Grid + random search ✅ | Not Bayesian |
| **Plotting/analytics** | Detailed per-trade analysis, profit by pair | Equity curve, allocation, sector/geography/asset-class | No per-trade attribution |
| **Notifications** | Telegram bot (full control + commands) | Telegram bot (chat + approvals) + webhook + email ✅ | Comparable |
| **Maturity** | Years of production use, large community | New project | Less hardened |

Where JARVIS is **ahead** of Freqtrade: natural-language reasoning and thesis
generation, macro-regime analysis, live web-search news synthesis, a written
investment journal it learns from, multi-asset focus (equities/ETFs vs
crypto-first), and a conversational dashboard. The two are complementary:
Freqtrade is the better *executor* of a fixed quantitative edge; JARVIS is the
better *analyst and allocator*.

Most of this list is now implemented: technical indicators, the full order
type set (stop-loss / trailing / take-profit / limit / stop / OCO), a
signal-level backtester, **parameter optimization**, **crypto/multi-exchange
execution via CCXT**, and a **Telegram interface**. The main remaining
Freqtrade edges are tick-level backtesting, websocket price streaming, and
Bayesian (vs grid) optimization.

## Roadmap / known gaps

Previously listed gaps now shipped: backtesting, alerts (webhook + email),
sector exposure, chat persistence, dashboard auth, realistic paper fills,
Docker, local-model support (Ollama), and the **quant layer — technical
indicators, stop-loss/trailing/take-profit protective orders, and a
signal-level strategy backtester, parameter optimization (grid + random),
limit/stop/OCO resting orders, time-based ROI exits, crypto execution (CCXT),
geography/asset-class exposure, and a Telegram bot**. Still on the list:

- **Tick-level backtesting** — engine is signal/daily-bar level.
- **Bayesian optimization** — current Hyperopt is grid + random search.
- **Websocket price streaming** — quotes are polled (60s cache).
- **Factor exposure** — sector/geography/asset-class exist; no factor model.
- **Multi-user support** — single portfolio, single token, single owner.

## Disclaimer

This is research/educational software, not financial advice. Markets involve
risk of loss; an LLM's judgment is fallible and market data can be delayed or
wrong. Keep paper mode on until you have validated behavior you trust, and
never allocate money you cannot afford to lose.
