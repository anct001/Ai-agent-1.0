"""Risk manager — the hard gate between the agent's intent and execution.

Every order the agent proposes is validated here BEFORE it reaches a broker.
The model can argue for a trade; it cannot override these limits.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import RiskLimits
from .portfolio import Portfolio


@dataclass
class OrderCheck:
    approved: bool
    reason: str


class RiskManager:
    def __init__(self, limits: RiskLimits):
        self.limits = limits

    def validate(
        self,
        portfolio: Portfolio,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        equity: float,
    ) -> OrderCheck:
        symbol = symbol.upper()

        if side not in ("buy", "sell"):
            return OrderCheck(False, f"Invalid side {side!r}")
        if qty <= 0:
            return OrderCheck(False, "Quantity must be positive")
        if price <= 0:
            return OrderCheck(False, f"No valid market price for {symbol}")
        if equity <= 0:
            return OrderCheck(False, "Account equity is zero or negative")

        if portfolio.trades_today() >= self.limits.max_orders_per_day:
            return OrderCheck(
                False,
                f"Daily order limit reached ({self.limits.max_orders_per_day})",
            )

        order_value = qty * price
        max_order = self.limits.max_order_pct * equity
        if order_value > max_order + 1e-6:
            return OrderCheck(
                False,
                f"Order value ${order_value:,.2f} exceeds per-order limit "
                f"${max_order:,.2f} ({self.limits.max_order_pct:.0%} of equity)",
            )

        if side == "buy":
            if order_value > portfolio.cash + 1e-6:
                return OrderCheck(
                    False,
                    f"Insufficient cash: order ${order_value:,.2f}, "
                    f"cash ${portfolio.cash:,.2f}",
                )

            min_cash = self.limits.min_cash_pct * equity
            if portfolio.cash - order_value < min_cash - 1e-6:
                return OrderCheck(
                    False,
                    f"Order would breach the cash reserve floor of ${min_cash:,.2f} "
                    f"({self.limits.min_cash_pct:.0%} of equity)",
                )

            resulting = portfolio.position_value(symbol, price) + order_value
            max_position = self.limits.max_position_pct * equity
            if resulting > max_position + 1e-6:
                return OrderCheck(
                    False,
                    f"Resulting {symbol} exposure ${resulting:,.2f} exceeds the "
                    f"single-position limit ${max_position:,.2f} "
                    f"({self.limits.max_position_pct:.0%} of equity)",
                )
        else:  # sell
            pos = portfolio.positions.get(symbol)
            held = pos.qty if pos else 0.0
            if qty > held + 1e-9:
                return OrderCheck(
                    False, f"Cannot sell {qty} {symbol}: holding {held}"
                )

        return OrderCheck(True, "Within risk limits")

    def describe(self) -> dict:
        return {
            "max_order_pct_of_equity": self.limits.max_order_pct,
            "max_position_pct_of_equity": self.limits.max_position_pct,
            "min_cash_reserve_pct": self.limits.min_cash_pct,
            "max_orders_per_day": self.limits.max_orders_per_day,
        }
