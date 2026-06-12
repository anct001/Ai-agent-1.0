"""Paper broker — simulated fills at live market prices, recorded locally."""

from __future__ import annotations

from typing import Callable

from ..portfolio import Portfolio
from .base import Fill


class PaperBroker:
    name = "paper"

    def __init__(self, portfolio: Portfolio, price_fn: Callable[[str], float]):
        self.portfolio = portfolio
        self.price_fn = price_fn

    def execute_order(
        self, symbol: str, side: str, qty: float, rationale: str
    ) -> Fill:
        symbol = symbol.upper()
        price = self.price_fn(symbol)
        self.portfolio.apply_fill(symbol, side, qty, price, rationale)
        return Fill(
            symbol=symbol, side=side, qty=qty, price=price, value=qty * price
        )
