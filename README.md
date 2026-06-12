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
python -m jarvis dashboard         # web dashboard at http://127.0.0.1:8000
python -m jarvis chat              # interactive terminal session
python -m jarvis analyze NVDA      # VC-style deep-dive on one ticker
python -m jarvis briefing          # daily macro + portfolio briefing
python -m jarvis auto --once       # one autonomous management cycle
python -m jarvis auto              # autonomous loop (daily by default)
python -m jarvis portfolio         # print holdings (no LLM call)
```

## Web dashboard

`python -m jarvis dashboard` serves a dark-themed single-page app:

- **Overview** — KPI cards (equity, cash, invested, unrealized P&L, daily
  trade budget), an **equity curve vs the S&P 500** (both indexed to 100),
  an **allocation donut**, live **macro regime tiles** (yield curve with an
  inversion signal, VIX, credit, dollar, oil, gold, bitcoin), positions
  marked to market, and the active risk limits.
- **Chat** — talk to the agent in the browser with streamed responses and
  tool-call indicators, plus one-click quick actions (daily briefing,
  portfolio review, "find an asymmetric bet").
- **Order approvals in the browser** — when the agent wants to trade, a
  modal shows the order, conviction, and rationale; nothing executes until
  you click Approve (denials and 5-minute timeouts both cancel the order).
- **Journal** — every recorded thesis (with conviction badge, horizon, and
  invalidation condition) and lessons learned.
- **Trades** — the full ledger with per-trade rationales.

The equity curve builds up day over day: each dashboard load snapshots
total equity alongside the S&P 500 close into `data/equity_history.json`.

> The dashboard binds to `127.0.0.1` and has **no authentication** — it can
> approve trades, so don't expose it to a network without putting auth in
> front of it.

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
| `jarvis/brokers/` | `PaperBroker` (default, simulated fills at live prices) and optional `AlpacaBroker` |
| `jarvis/history.py` | Daily equity-curve snapshots with S&P 500 benchmark, normalized for charting |
| `jarvis/server.py` | FastAPI backend: REST + SSE chat streaming + browser order-approval hub |
| `jarvis/web/` | Dashboard SPA (vanilla JS + Chart.js, no build step) |
| `jarvis/cli.py` | CLI, interactive order approval, autonomous scheduler, dashboard launcher |

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

## Roadmap / known gaps

Honest self-assessment of what's still missing:

- **Backtesting** — no way to replay a strategy against history before
  trusting it forward; the highest-value next addition.
- **Alerts** — no push/email when a thesis invalidation triggers or a
  position breaches a drawdown threshold between cycles.
- **Sector / factor exposure** — allocation is per-symbol only; no view of
  concentration by sector, geography, or factor.
- **Chat persistence** — web/CLI conversations reset per process; the
  journal persists, the dialogue doesn't.
- **Dashboard auth** — localhost-only by design until auth exists.
- **Realistic fills** — paper fills assume zero slippage and no commissions.
- **Deployment** — no Dockerfile or systemd unit for running the autonomous
  loop unattended yet.

## Disclaimer

This is research/educational software, not financial advice. Markets involve
risk of loss; an LLM's judgment is fallible and market data can be delayed or
wrong. Keep paper mode on until you have validated behavior you trust, and
never allocate money you cannot afford to lose.
