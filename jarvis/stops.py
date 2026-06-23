"""Protective orders: stop-loss, trailing-stop, take-profit.

Freqtrade's core risk feature. The agent (or user) attaches protective levels
to a position; a monitor checks them against live prices and auto-exits the
full position when one triggers. Selling reduces exposure, so these execute
without human approval — that is the point of a stop.

State persists to data/stops.json. Trailing stops track a high-water mark.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


class StopBook:
    def __init__(self, path: Path):
        self.path = path
        self.orders: dict[str, dict] = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except json.JSONDecodeError:
                return {}
        return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.orders, indent=2))

    def set(
        self,
        symbol: str,
        stop_loss_pct: float | None = None,
        trailing_stop_pct: float | None = None,
        take_profit_pct: float | None = None,
    ) -> dict:
        symbol = symbol.upper()
        order = self.orders.get(symbol, {})
        if stop_loss_pct is not None:
            order["stop_loss_pct"] = float(stop_loss_pct)
        if trailing_stop_pct is not None:
            order["trailing_stop_pct"] = float(trailing_stop_pct)
        if take_profit_pct is not None:
            order["take_profit_pct"] = float(take_profit_pct)
        order.setdefault("high_water_mark", 0.0)
        self.orders[symbol] = order
        self._save()
        return {"symbol": symbol, **order}

    def remove(self, symbol: str) -> None:
        if self.orders.pop(symbol.upper(), None) is not None:
            self._save()

    def all(self) -> dict[str, dict]:
        return dict(self.orders)

    def evaluate(self, symbol: str, avg_cost: float, price: float) -> str | None:
        """Update trailing high-water mark and return a trigger reason, or None."""
        symbol = symbol.upper()
        order = self.orders.get(symbol)
        if not order:
            return None

        hwm = max(order.get("high_water_mark", 0.0), price)
        if hwm != order.get("high_water_mark"):
            order["high_water_mark"] = hwm
            self._save()

        sl = order.get("stop_loss_pct")
        if sl is not None and price <= avg_cost * (1 - sl / 100.0):
            return f"stop-loss hit ({sl:.1f}% below ${avg_cost:,.2f} cost)"

        tp = order.get("take_profit_pct")
        if tp is not None and price >= avg_cost * (1 + tp / 100.0):
            return f"take-profit hit ({tp:.1f}% above ${avg_cost:,.2f} cost)"

        ts = order.get("trailing_stop_pct")
        if ts is not None and hwm > 0 and price <= hwm * (1 - ts / 100.0):
            return f"trailing stop hit ({ts:.1f}% below peak ${hwm:,.2f})"

        return None


class StopEngine:
    """Checks every position with a protective order and auto-exits triggers."""

    def __init__(self, stop_book: StopBook, portfolio, broker, price_fn: Callable[[str], float]):
        self.book = stop_book
        self.portfolio = portfolio
        self.broker = broker
        self.price_fn = price_fn

    def run(self) -> list[dict]:
        """Returns a list of executed protective exits (possibly empty)."""
        executed = []
        for symbol, pos in list(self.portfolio.positions.items()):
            if symbol not in self.book.orders:
                continue
            try:
                price = self.price_fn(symbol)
            except Exception:
                continue
            reason = self.book.evaluate(symbol, pos.avg_cost, price)
            if not reason:
                continue
            qty = pos.qty
            try:
                fill = self.broker.execute_order(
                    symbol, "sell", qty, f"Protective exit: {reason}"
                )
            except Exception as exc:
                executed.append({"symbol": symbol, "error": str(exc), "reason": reason})
                continue
            self.book.remove(symbol)
            executed.append(
                {
                    "symbol": symbol,
                    "qty": qty,
                    "exit_price": round(fill.price, 4),
                    "reason": reason,
                }
            )
        return executed
