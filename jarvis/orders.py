"""Resting orders: limit, stop, and OCO (one-cancels-other).

Freqtrade-style pending orders that aren't filled immediately but wait for a
price trigger. A monitor (`OrderEngine`) checks them on the same cadence as
protective stops (dashboard alert polls + autonomous cycles) and fills them
through the broker — re-validating buys against the risk manager at fill time.

Trigger semantics (the four useful combinations):
  limit buy  — fill when price <= limit  (buy the dip)
  limit sell — fill when price >= limit  (take profit)
  stop  buy  — fill when price >= stop   (breakout entry)
  stop  sell — fill when price <= stop   (breakdown / stop exit)

OCO: two linked orders sharing an `oco_group`; when one fills, the other is
cancelled. The classic use is bracketing a long with a take-profit limit-sell
and a stop-loss stop-sell.

State persists to data/pending_orders.json.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


class OrderBook:
    def __init__(self, path: Path):
        self.path = path
        self.orders: list[dict] = self._load()

    def _load(self) -> list[dict]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except json.JSONDecodeError:
                return []
        return []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.orders, indent=2))

    def add(
        self,
        symbol: str,
        side: str,
        trigger: str,
        price: float,
        qty: float,
        rationale: str = "",
        conviction: str = "medium",
        oco_group: str | None = None,
    ) -> dict:
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        if trigger not in ("limit", "stop"):
            raise ValueError("trigger must be 'limit' or 'stop'")
        if price <= 0 or qty <= 0:
            raise ValueError("price and qty must be positive")
        order = {
            "id": uuid.uuid4().hex[:8],
            "symbol": symbol.upper(),
            "side": side,
            "trigger": trigger,
            "price": float(price),
            "qty": float(qty),
            "rationale": rationale,
            "conviction": conviction,
            "oco_group": oco_group,
            "created": datetime.now(timezone.utc).isoformat(),
        }
        self.orders.append(order)
        self._save()
        return order

    def add_oco(
        self,
        symbol: str,
        qty: float,
        take_profit_price: float,
        stop_loss_price: float,
        rationale: str = "",
    ) -> list[dict]:
        """Bracket an existing long: sell at TP (limit) or SL (stop)."""
        group = uuid.uuid4().hex[:8]
        tp = self.add(symbol, "sell", "limit", take_profit_price, qty, rationale, oco_group=group)
        sl = self.add(symbol, "sell", "stop", stop_loss_price, qty, rationale, oco_group=group)
        return [tp, sl]

    def cancel(self, order_id: str) -> bool:
        before = len(self.orders)
        self.orders = [o for o in self.orders if o["id"] != order_id]
        if len(self.orders) != before:
            self._save()
            return True
        return False

    def all(self) -> list[dict]:
        return list(self.orders)

    @staticmethod
    def is_triggered(order: dict, price: float) -> bool:
        side, trigger, level = order["side"], order["trigger"], order["price"]
        if side == "buy":
            return price <= level if trigger == "limit" else price >= level
        return price >= level if trigger == "limit" else price <= level


class OrderEngine:
    def __init__(self, book: OrderBook, portfolio, broker, risk, price_fn: Callable[[str], float]):
        self.book = book
        self.portfolio = portfolio
        self.broker = broker
        self.risk = risk
        self.price_fn = price_fn

    def run(self) -> list[dict]:
        """Fill any triggered orders; return a list of fill/cancel events."""
        events = []
        for order in list(self.book.orders):
            if order not in self.book.orders:
                continue  # cancelled as an OCO sibling earlier this pass
            try:
                price = self.price_fn(order["symbol"])
            except Exception:
                continue
            if not self.book.is_triggered(order, price):
                continue

            symbol, side, qty = order["symbol"], order["side"], order["qty"]

            if side == "buy":
                equity = self.portfolio.equity(self.price_fn)
                check = self.risk.validate(self.portfolio, symbol, side, qty, price, equity)
                if not check.approved:
                    self.book.cancel(order["id"])
                    events.append(
                        {"id": order["id"], "symbol": symbol, "status": "cancelled",
                         "reason": f"risk: {check.reason}"}
                    )
                    continue
            else:  # sell — clamp to held quantity
                pos = self.portfolio.positions.get(symbol)
                held = pos.qty if pos else 0.0
                if held <= 0:
                    self.book.cancel(order["id"])
                    events.append(
                        {"id": order["id"], "symbol": symbol, "status": "cancelled",
                         "reason": "no position to sell"}
                    )
                    continue
                qty = min(qty, held)

            try:
                fill = self.broker.execute_order(
                    symbol, side, qty, order.get("rationale", "pending order")
                )
            except Exception as exc:
                events.append({"id": order["id"], "symbol": symbol, "status": "error", "reason": str(exc)})
                continue

            self.book.cancel(order["id"])
            # OCO: cancel siblings sharing the group.
            if order.get("oco_group"):
                for sib in list(self.book.orders):
                    if sib.get("oco_group") == order["oco_group"]:
                        self.book.cancel(sib["id"])
            events.append(
                {
                    "id": order["id"],
                    "symbol": symbol,
                    "side": side,
                    "qty": qty,
                    "fill_price": round(fill.price, 4),
                    "trigger": order["trigger"],
                    "status": "filled",
                }
            )
        return events
