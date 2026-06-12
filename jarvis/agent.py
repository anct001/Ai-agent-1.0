"""The agentic core: Claude + tools + risk-gated execution.

A manual agentic loop (rather than the SDK tool runner) so that order
placement can be intercepted for risk validation and human approval before
anything executes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import anthropic

from .config import Settings
from .memory import Journal
from .portfolio import Portfolio
from .prompts import SYSTEM_PROMPT
from .risk import RiskManager
from .tools import macro, market_data

# Client-side tool schemas. Descriptions are prescriptive about WHEN to call
# each tool — recent Opus models reach for tools conservatively otherwise.
TOOLS = [
    {
        "name": "get_quote",
        "description": (
            "Get live price, 1-day/1-month change, 52-week range, and market "
            "cap for one or more tickers. Call this before discussing any "
            "specific stock's price or placing any order — never quote prices "
            "from memory."
        ),
        "input_schema": {
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
    },
    {
        "name": "get_price_history",
        "description": (
            "Get historical price summary for a ticker: total return, "
            "volatility, max drawdown, 50/200-day moving averages, and recent "
            "closes. Call this when assessing trend, momentum, or risk of a "
            "specific name."
        ),
        "input_schema": {
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
    },
    {
        "name": "get_fundamentals",
        "description": (
            "Get valuation and quality metrics for a ticker: P/E, margins, "
            "revenue growth, free cash flow, debt, ownership. Call this when "
            "building or updating an investment thesis on a company."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_macro_snapshot",
        "description": (
            "Get the current macro regime: equity indices, 10Y/3M yields and "
            "the yield-curve spread, VIX, high-yield credit, dollar, oil, "
            "gold, bitcoin — each with 1-day/1-month/6-month changes. Call "
            "this at the start of any session that involves market analysis "
            "or trading decisions."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_portfolio",
        "description": (
            "Get the current portfolio: cash, total equity, every position "
            "marked to market with unrealized P&L, and today's trade count. "
            "Call this before any trade decision and whenever the user asks "
            "about holdings or performance."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "place_order",
        "description": (
            "Place a market order. The order is validated by an independent "
            "risk manager (position-size, cash-reserve, and daily-trade "
            "limits) and may require human approval; a rejection returns the "
            "reason. Only call this after checking the portfolio and a live "
            "quote, and always include a substantive rationale."
        ),
        "input_schema": {
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
    },
    {
        "name": "run_backtest",
        "description": (
            "Backtest a target-weight allocation against historical prices "
            "before committing capital: returns CAGR, volatility, Sharpe, "
            "max drawdown, and the comparison vs a benchmark. Call this "
            "whenever you propose a portfolio allocation or want to sanity-"
            "check a strategy against history. Weights are fractions of "
            "equity; any remainder is held as cash."
        ),
        "input_schema": {
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
    },
    {
        "name": "record_thesis",
        "description": (
            "Persist an investment thesis to the journal. Call this whenever "
            "you form or materially revise a view on a name — before any "
            "related order."
        ),
        "input_schema": {
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
    },
    {
        "name": "record_lesson",
        "description": (
            "Persist a lesson learned to the journal. Call this after a "
            "thesis resolves (win or loss) or when you notice a repeatable "
            "mistake or insight."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lesson": {"type": "string"},
                "context": {"type": "string"},
            },
            "required": ["lesson"],
        },
    },
    {
        "name": "read_journal",
        "description": (
            "Read recent theses and lessons from the journal. Call this at "
            "the start of a session and before re-analyzing any name you may "
            "have covered before."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Optional: filter theses to one ticker",
                }
            },
        },
    },
    # Server-side tool: Anthropic executes searches; results return with
    # citations. Gives the agent real-time news/trend awareness.
    {"type": "web_search_20260209", "name": "web_search"},
]

MAX_ITERATIONS = 40


class InvestmentAgent:
    def __init__(
        self,
        settings: Settings,
        portfolio: Portfolio,
        broker,
        risk: RiskManager,
        journal: Journal,
        approve_fn: Callable[[dict], bool] | None = None,
        history_path: Path | None = None,
    ):
        """approve_fn receives the order dict and returns True to execute.
        When None, orders auto-approve (use only with the paper broker).
        history_path, when set, persists the conversation across restarts."""
        self.client = anthropic.Anthropic()
        self.settings = settings
        self.portfolio = portfolio
        self.broker = broker
        self.risk = risk
        self.journal = journal
        self.approve_fn = approve_fn
        self.history_path = history_path
        self.messages: list[dict] = self._load_history()

    # ---------- tool dispatch ----------

    def _tool_get_quote(self, args: dict):
        return market_data.get_quote(args["symbols"])

    def _tool_get_price_history(self, args: dict):
        return market_data.get_price_history(
            args["symbol"], args.get("period", "1y")
        )

    def _tool_get_fundamentals(self, args: dict):
        return market_data.get_fundamentals(args["symbol"])

    def _tool_get_macro_snapshot(self, args: dict):
        return macro.get_macro_snapshot()

    def _tool_get_portfolio(self, args: dict):
        snap = self.portfolio.snapshot(market_data.last_price)
        snap["broker"] = self.broker.name
        snap["risk_limits"] = self.risk.describe()
        snap["sector_allocation"] = market_data.sector_allocation(snap["positions"])
        return snap

    def _tool_run_backtest(self, args: dict):
        from .backtest import run_backtest

        result = run_backtest(
            args["weights"],
            period=args.get("period", "5y"),
            rebalance=args.get("rebalance", "monthly"),
            benchmark_symbol=args.get("benchmark", "SPY"),
        )
        result.pop("curve", None)  # chart data is for the UI, not the model
        return result

    def _tool_place_order(self, args: dict):
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
            "conviction": args["conviction"],
            "rationale": args["rationale"],
        }
        if self.approve_fn is not None and not self.approve_fn(order_view):
            return {
                "status": "denied_by_human",
                "reason": "The human operator declined this order.",
            }

        fill = self.broker.execute_order(symbol, side, qty, args["rationale"])
        return {
            "status": "filled",
            "broker": self.broker.name,
            "symbol": fill.symbol,
            "side": fill.side,
            "qty": fill.qty,
            "fill_price": round(fill.price, 4),
            "value": round(fill.value, 2),
        }

    def _tool_record_thesis(self, args: dict):
        return self.journal.record_thesis(
            args["symbol"],
            args["thesis"],
            args["conviction"],
            args["horizon"],
            args["invalidation"],
        )

    def _tool_record_lesson(self, args: dict):
        return self.journal.record_lesson(args["lesson"], args.get("context", ""))

    def _tool_read_journal(self, args: dict):
        if args.get("symbol"):
            return {"theses": self.journal.theses_for(args["symbol"])}
        return self.journal.read()

    def _execute_tool(self, name: str, args: dict):
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")
        return handler(args)

    # ---------- conversation persistence ----------

    MAX_HISTORY_MESSAGES = 60

    def _load_history(self) -> list[dict]:
        if self.history_path and self.history_path.exists():
            try:
                return json.loads(self.history_path.read_text())
            except json.JSONDecodeError:
                return []
        return []

    @staticmethod
    def _serializable(messages: list[dict]) -> list[dict]:
        out = []
        for msg in messages:
            content = msg["content"]
            if isinstance(content, list):
                content = [
                    b.model_dump(exclude_none=True) if hasattr(b, "model_dump") else b
                    for b in content
                ]
            out.append({"role": msg["role"], "content": content})
        return out

    def _trim_history(self) -> None:
        """Bound context size; cut only at a real user-text message so
        tool_use/tool_result pairs are never orphaned."""
        if len(self.messages) <= self.MAX_HISTORY_MESSAGES:
            return
        for i in range(len(self.messages) - self.MAX_HISTORY_MESSAGES, len(self.messages)):
            msg = self.messages[i]
            if msg["role"] == "user" and isinstance(msg["content"], str):
                self.messages = self.messages[i:]
                return

    def _save_history(self) -> None:
        self._trim_history()
        # Normalize to plain dicts in memory too — the API accepts dict
        # content, and it keeps downstream handling uniform.
        self.messages = self._serializable(self.messages)
        if self.history_path:
            self.history_path.write_text(json.dumps(self.messages))

    def transcript(self) -> list[dict]:
        """Displayable history: user text and assistant text only."""
        out = []
        for msg in self._serializable(self.messages):
            if msg["role"] == "user" and isinstance(msg["content"], str):
                out.append({"role": "user", "text": msg["content"]})
            elif msg["role"] == "assistant":
                text = "".join(
                    b.get("text", "")
                    for b in msg["content"]
                    if isinstance(b, dict) and b.get("type") == "text"
                )
                if text.strip():
                    out.append({"role": "agent", "text": text})
        return out

    # ---------- agent loop ----------

    def run_turn(self, user_message: str, on_text: Callable[[str], None]) -> str:
        """Run one user turn through the full agentic loop.

        Streams assistant text to on_text as it arrives; returns the final
        accumulated text of the last assistant message.
        """
        self.messages.append({"role": "user", "content": user_message})

        for _ in range(MAX_ITERATIONS):
            with self.client.messages.stream(
                model=self.settings.model,
                max_tokens=self.settings.max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                thinking={"type": "adaptive"},
                output_config={"effort": self.settings.effort},
                tools=TOOLS,
                messages=self.messages,
            ) as stream:
                for text in stream.text_stream:
                    on_text(text)
                response = stream.get_final_message()

            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "tool_use":
                results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    on_text(f"\n[tool: {block.name}]\n")
                    try:
                        output = self._execute_tool(block.name, block.input)
                        results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(output, default=str),
                            }
                        )
                    except Exception as exc:
                        results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": f"Error: {exc}",
                                "is_error": True,
                            }
                        )
                self.messages.append({"role": "user", "content": results})
                continue

            if response.stop_reason == "pause_turn":
                # Server-side tool (web_search) paused mid-loop; re-send to
                # let the server resume where it left off.
                continue

            if response.stop_reason == "refusal":
                on_text("\n[The model declined this request for safety reasons.]\n")

            break  # end_turn, max_tokens, refusal — turn is over

        self._save_history()
        last = self.messages[-1]
        if last["role"] != "assistant":
            return ""
        # After _save_history, content blocks are plain dicts.
        return next(
            (
                b["text"]
                for b in last["content"]
                if isinstance(b, dict) and b.get("type") == "text"
            ),
            "",
        )

    def reset(self) -> None:
        self.messages = []
        if self.history_path and self.history_path.exists():
            self.history_path.unlink()
