"""Paper broker — simulated fills at live market prices, recorded locally.

Fills are made realistic with configurable slippage (applied against the
trader: buys fill above the quote, sells below) and a flat commission.
"""

from __future__ import annotations

from typing import Callable

from ..portfolio import Portfolio
from .base import Fill


class PaperBroker:
    name = "paper"

    def __init__(
        self,
        portfolio: Portfolio,
        price_fn: Callable[[str], float],
        slippage_bps: float = 0.0,
        commission: float = 0.0,
    ):
        self.portfolio = portfolio
        self.price_fn = price_fn
        self.slippage_bps = slippage_bps
        self.commission = commission

    def execute_order(
        self, symbol: str, side: str, qty: float, rationale: str
    ) -> Fill:
        symbol = symbol.upper()
        quote = self.price_fn(symbol)
        slip = self.slippage_bps / 10_000.0
        price = quote * (1 + slip) if side == "buy" else quote * (1 - slip)
        self.portfolio.apply_fill(
            symbol, side, qty, price, rationale, fee=self.commission
        )
        return Fill(
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            value=qty * price,
            fee=self.commission,
        )
