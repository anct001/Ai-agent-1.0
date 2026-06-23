"""Shared tool surface for every LLM backend.

The tool *implementations* and their JSON schemas live here once, so the
Claude (Anthropic) engine and the local (Ollama) engine expose an identical
set of capabilities and identical risk-gated execution. Only the schema
wrapper differs per provider, built from one source of truth below.
"""

from __future__ import annotations

import json
from typing import Callable

from .memory import Journal
from .portfolio import Portfolio
from .risk import RiskManager
from .tools import macro, market_data

# Single source of truth: (name, description, json_schema). Descriptions are
# prescriptive about WHEN to call each tool.
_TOOL_DEFS = [
    (
        "get_quote",
        "Get live price, 1-day/1-month change, 52-week range, and market cap "
        "for one or more tickers. Call this before discussing any specific "
        "stock's price or placing any order — never quote prices from memory.",
        {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ticker symbols, e.g. ['NVDA', 'MSFT']",
                }
            },
            "required": ["symbols"],
        },
    ),
    (
        "get_price_history",
        "Get historical price summary for a ticker: total return, volatility, "
        "max drawdown, 50/200-day moving averages, and recent closes. Call "
        "this when assessing trend, momentum, or risk of a specific name.",
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "period": {
                    "type": "string",
                    "enum": ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"],
                    "description": "Lookback window (default 1y)",
                },
            },
            "required": ["symbol"],
        },
    ),
    (
        "get_fundamentals",
        "Get valuation and quality metrics for a ticker: P/E, margins, revenue "
        "growth, free cash flow, debt, ownership. Call this when building or "
        "updating an investment thesis on a company.",
        {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    ),
    (
        "get_macro_snapshot",
        "Get the current macro regime: equity indices, 10Y/3M yields and the "
        "yield-curve spread, VIX, high-yield credit, dollar, oil, gold, "
        "bitcoin — each with 1-day/1-month/6-month changes. Call this at the "
        "start of any session that involves market analysis or trading.",
        {"type": "object", "properties": {}},
    ),
    (
        "get_portfolio",
        "Get the current portfolio: cash, total equity, every position marked "
        "to market with unrealized P&L, sector allocation, and today's trade "
        "count. Call this before any trade decision and whenever the user asks "
        "about holdings or performance.",
        {"type": "object", "properties": {}},
    ),
    (
        "place_order",
        "Place a market order. The order is validated by an independent risk "
        "manager (position-size, cash-reserve, and daily-trade limits) and may "
        "require human approval; a rejection returns the reason. Only call "
        "this after checking the portfolio and a live quote, and always "
        "include a substantive rationale.",
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string", "enum": ["buy", "sell"]},
                "qty": {
                    "type": "number",
                    "description": "Number of shares (fractional allowed)",
                },
                "rationale": {
                    "type": "string",
                    "description": "One-paragraph thesis-linked justification",
                },
                "conviction": {
                    "type": "string",
                    "enum": ["high", "medium", "low", "speculative"],
                },
            },
            "required": ["symbol", "side", "qty", "rationale", "conviction"],
        },
    ),
    (
        "run_backtest",
        "Backtest a target-weight allocation against historical prices before "
        "committing capital: returns CAGR, volatility, Sharpe, max drawdown, "
        "and the comparison vs a benchmark. Call this whenever you propose a "
        "portfolio allocation. Weights are fractions of equity; any remainder "
        "is held as cash.",
        {
            "type": "object",
            "properties": {
                "weights": {
                    "type": "object",
                    "description": 'e.g. {"NVDA": 0.3, "MSFT": 0.3, "GLD": 0.2}',
                    "additionalProperties": {"type": "number"},
                },
                "period": {
                    "type": "string",
                    "enum": ["1y", "2y", "5y", "10y", "max"],
                    "description": "Lookback window (default 5y)",
                },
                "rebalance": {
                    "type": "string",
                    "enum": ["weekly", "monthly", "quarterly"],
                    "description": "Rebalancing cadence (default monthly)",
                },
                "benchmark": {
                    "type": "string",
                    "description": "Benchmark ticker (default SPY)",
                },
            },
            "required": ["weights"],
        },
    ),
    (
        "get_indicators",
        "Get technical indicators for a ticker: RSI, MACD, Bollinger Bands, "
        "50/200-day SMAs, ATR, plus a plain-language signal read. Call this "
        "when assessing entry/exit timing or momentum for a name.",
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "period": {
                    "type": "string",
                    "enum": ["3mo", "6mo", "1y", "2y", "5y"],
                    "description": "Lookback window (default 1y)",
                },
            },
            "required": ["symbol"],
        },
    ),
    (
        "backtest_strategy",
        "Backtest a rule-based technical strategy on one ticker over history, "
        "with fees and an optional stop-loss: returns win rate, number of "
        "trades, CAGR/Sharpe/drawdown, and the comparison vs buy-and-hold. "
        "Use this to validate a timing strategy before trading it.",
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "strategy": {
                    "type": "string",
                    "enum": ["sma_cross", "rsi", "macd_cross", "bollinger"],
                },
                "period": {
                    "type": "string",
                    "enum": ["1y", "2y", "5y", "10y", "max"],
                    "description": "Lookback window (default 5y)",
                },
                "stop_loss_pct": {
                    "type": "number",
                    "description": "Optional stop-loss percent (e.g. 8 for -8%)",
                },
            },
            "required": ["symbol", "strategy"],
        },
    ),
    (
        "set_protective_orders",
        "Attach protective exit levels to a held position: stop-loss, "
        "trailing-stop, and/or take-profit (each a percent). A monitor "
        "auto-sells the full position when a level triggers. Set these right "
        "after opening a position to cap downside.",
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "stop_loss_pct": {
                    "type": "number",
                    "description": "Exit if price falls this % below avg cost",
                },
                "trailing_stop_pct": {
                    "type": "number",
                    "description": "Exit if price falls this % below its peak",
                },
                "take_profit_pct": {
                    "type": "number",
                    "description": "Exit if price rises this % above avg cost",
                },
            },
            "required": ["symbol"],
        },
    ),
    (
        "get_protective_orders",
        "List the protective orders (stop-loss / trailing-stop / take-profit) "
        "currently attached to positions.",
        {"type": "object", "properties": {}},
    ),
    (
        "record_thesis",
        "Persist an investment thesis to the journal. Call this whenever you "
        "form or materially revise a view on a name — before any related order.",
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "thesis": {"type": "string"},
                "conviction": {
                    "type": "string",
                    "enum": ["high", "medium", "low", "speculative"],
                },
                "horizon": {
                    "type": "string",
                    "description": "e.g. '6-12 months', '3-5 years'",
                },
                "invalidation": {
                    "type": "string",
                    "description": "Observable condition that kills the thesis",
                },
            },
            "required": ["symbol", "thesis", "conviction", "horizon", "invalidation"],
        },
    ),
    (
        "record_lesson",
        "Persist a lesson learned to the journal. Call this after a thesis "
        "resolves (win or loss) or when you notice a repeatable mistake.",
        {
            "type": "object",
            "properties": {
                "lesson": {"type": "string"},
                "context": {"type": "string"},
            },
            "required": ["lesson"],
        },
    ),
    (
        "read_journal",
        "Read recent theses and lessons from the journal. Call this at the "
        "start of a session and before re-analyzing a name you may have "
        "covered before.",
        {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Optional: filter theses to one ticker",
                }
            },
        },
    ),
]


def anthropic_tools(include_web_search: bool = True) -> list[dict]:
    tools = [
        {"name": n, "description": d, "input_schema": s} for n, d, s in _TOOL_DEFS
    ]
    if include_web_search:
        # Server-side tool: Anthropic runs the search and returns citations.
        tools.append({"type": "web_search_20260209", "name": "web_search"})
    return tools


def openai_tools() -> list[dict]:
    """OpenAI/Ollama function-calling format. No web_search — that tool is
    executed by Anthropic's servers and has no local equivalent."""
    return [
        {
            "type": "function",
            "function": {"name": n, "description": d, "parameters": s},
        }
        for n, d, s in _TOOL_DEFS
    ]


class Toolkit:
    """Executes tool calls against the portfolio/broker/journal, applying the
    risk gate and human-approval hook. Backend-agnostic."""

    def __init__(
        self,
        portfolio: Portfolio,
        broker,
        risk: RiskManager,
        journal: Journal,
        approve_fn: Callable[[dict], bool] | None = None,
        stop_book=None,
    ):
        self.portfolio = portfolio
        self.broker = broker
        self.risk = risk
        self.journal = journal
        self.approve_fn = approve_fn
        self.stop_book = stop_book

    def execute(self, name: str, args: dict):
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")
        return handler(args or {})

    def execute_json(self, name: str, args: dict) -> str:
        """Run a tool and return a JSON string (the wire format both engines
        feed back to the model)."""
        try:
            return json.dumps(self.execute(name, args), default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # ---------- tool implementations ----------

    def _tool_get_quote(self, args):
        return market_data.get_quote(args["symbols"])

    def _tool_get_price_history(self, args):
        return market_data.get_price_history(args["symbol"], args.get("period", "1y"))

    def _tool_get_fundamentals(self, args):
        return market_data.get_fundamentals(args["symbol"])

    def _tool_get_macro_snapshot(self, args):
        return macro.get_macro_snapshot()

    def _tool_get_portfolio(self, args):
        snap = self.portfolio.snapshot(market_data.last_price)
        snap["broker"] = self.broker.name
        snap["risk_limits"] = self.risk.describe()
        snap["sector_allocation"] = market_data.sector_allocation(snap["positions"])
        return snap

    def _tool_run_backtest(self, args):
        from .backtest import run_backtest

        result = run_backtest(
            args["weights"],
            period=args.get("period", "5y"),
            rebalance=args.get("rebalance", "monthly"),
            benchmark_symbol=args.get("benchmark", "SPY"),
        )
        result.pop("curve", None)  # chart data is for the UI, not the model
        return result

    def _tool_place_order(self, args):
        symbol = args["symbol"].upper()
        side = args["side"]
        qty = float(args["qty"])

        price = market_data.last_price(symbol)
        equity = self.portfolio.equity(market_data.last_price)
        check = self.risk.validate(self.portfolio, symbol, side, qty, price, equity)
        if not check.approved:
            return {"status": "rejected_by_risk_manager", "reason": check.reason}

        order_view = {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "est_price": round(price, 2),
            "est_value": round(qty * price, 2),
            "conviction": args.get("conviction", "unspecified"),
            "rationale": args.get("rationale", ""),
        }
        if self.approve_fn is not None and not self.approve_fn(order_view):
            return {
                "status": "denied_by_human",
                "reason": "The human operator declined this order.",
            }

        fill = self.broker.execute_order(symbol, side, qty, args.get("rationale", ""))
        return {
            "status": "filled",
            "broker": self.broker.name,
            "symbol": fill.symbol,
            "side": fill.side,
            "qty": fill.qty,
            "fill_price": round(fill.price, 4),
            "value": round(fill.value, 2),
        }

    def _tool_get_indicators(self, args):
        from .tools import indicators

        return indicators.get_indicators(args["symbol"], args.get("period", "1y"))

    def _tool_backtest_strategy(self, args):
        from .strategy import run_strategy

        result = run_strategy(
            args["symbol"],
            strategy=args.get("strategy", "sma_cross"),
            period=args.get("period", "5y"),
            stop_loss_pct=args.get("stop_loss_pct"),
        )
        result.pop("curve", None)  # chart data is for the UI, not the model
        return result

    def _tool_set_protective_orders(self, args):
        if self.stop_book is None:
            return {"error": "protective orders not available in this context"}
        symbol = args["symbol"].upper()
        if symbol not in self.portfolio.positions:
            return {"error": f"No open position in {symbol} to protect"}
        return self.stop_book.set(
            symbol,
            stop_loss_pct=args.get("stop_loss_pct"),
            trailing_stop_pct=args.get("trailing_stop_pct"),
            take_profit_pct=args.get("take_profit_pct"),
        )

    def _tool_get_protective_orders(self, args):
        if self.stop_book is None:
            return {}
        return self.stop_book.all()

    def _tool_record_thesis(self, args):
        return self.journal.record_thesis(
            args["symbol"],
            args["thesis"],
            args["conviction"],
            args["horizon"],
            args["invalidation"],
        )

    def _tool_record_lesson(self, args):
        return self.journal.record_lesson(args["lesson"], args.get("context", ""))

    def _tool_read_journal(self, args):
        if args.get("symbol"):
            return {"theses": self.journal.theses_for(args["symbol"])}
        return self.journal.read()
