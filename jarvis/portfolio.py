"""Local portfolio ledger with JSON persistence.

This is the source of truth in paper mode and the local trade journal in
live mode. It deliberately has no third-party dependencies so it can be
tested offline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


@dataclass
class Position:
    qty: float
    avg_cost: float


class Portfolio:
    def __init__(self, path: Path, starting_cash: float = 100_000.0):
        self.path = path
        self.cash: float = starting_cash
        self.positions: dict[str, Position] = {}
        self.trades: list[dict] = []
        self._load()

    # ---------- persistence ----------

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text())
        self.cash = data["cash"]
        self.positions = {
            sym: Position(**pos) for sym, pos in data.get("positions", {}).items()
        }
        self.trades = data.get("trades", [])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "cash": self.cash,
            "positions": {
                sym: {"qty": p.qty, "avg_cost": p.avg_cost}
                for sym, p in self.positions.items()
            },
            "trades": self.trades,
        }
        self.path.write_text(json.dumps(data, indent=2))

    # ---------- queries ----------

    def position_value(self, symbol: str, price: float) -> float:
        pos = self.positions.get(symbol)
        return pos.qty * price if pos else 0.0

    def equity(self, price_fn: Callable[[str], float]) -> float:
        """Total account value: cash plus marked-to-market positions."""
        total = self.cash
        for sym, pos in self.positions.items():
            total += pos.qty * price_fn(sym)
        return total

    def trades_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        return sum(1 for t in self.trades if t["timestamp"].startswith(today))

    # ---------- mutations ----------

    def apply_fill(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        rationale: str = "",
        fee: float = 0.0,
    ) -> dict:
        """Record an executed fill, updating cash and positions.

        `fee` (commission) is deducted from cash on both sides.
        """
        symbol = symbol.upper()
        if side == "buy":
            cost = qty * price + fee
            if cost > self.cash + 1e-9:
                raise ValueError(
                    f"Insufficient cash: need ${cost:,.2f}, have ${self.cash:,.2f}"
                )
            pos = self.positions.get(symbol)
            if pos:
                new_qty = pos.qty + qty
                pos.avg_cost = (pos.qty * pos.avg_cost + qty * price) / new_qty
                pos.qty = new_qty
            else:
                self.positions[symbol] = Position(qty=qty, avg_cost=price)
            self.cash -= cost
        elif side == "sell":
            pos = self.positions.get(symbol)
            if not pos or pos.qty < qty - 1e-9:
                held = pos.qty if pos else 0.0
                raise ValueError(f"Insufficient shares: selling {qty}, hold {held}")
            pos.qty -= qty
            if pos.qty <= 1e-9:
                del self.positions[symbol]
            self.cash += qty * price - fee
        else:
            raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")

        trade = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "value": round(qty * price, 2),
            "fee": round(fee, 2),
            "rationale": rationale,
        }
        self.trades.append(trade)
        self.save()
        return trade

    # ---------- reporting ----------

    def snapshot(self, price_fn: Callable[[str], float]) -> dict:
        positions = []
        for sym, pos in sorted(self.positions.items()):
            price = price_fn(sym)
            value = pos.qty * price
            pnl = (price - pos.avg_cost) * pos.qty
            pnl_pct = (price / pos.avg_cost - 1) * 100 if pos.avg_cost else 0.0
            positions.append(
                {
                    "symbol": sym,
                    "qty": round(pos.qty, 4),
                    "avg_cost": round(pos.avg_cost, 2),
                    "price": round(price, 2),
                    "value": round(value, 2),
                    "unrealized_pnl": round(pnl, 2),
                    "unrealized_pnl_pct": round(pnl_pct, 2),
                }
            )
        equity = self.cash + sum(p["value"] for p in positions)
        return {
            "cash": round(self.cash, 2),
            "equity": round(equity, 2),
            "positions": positions,
            "trades_today": self.trades_today(),
            "total_trades": len(self.trades),
        }
