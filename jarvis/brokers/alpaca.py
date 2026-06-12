"""Alpaca broker adapter (optional, used only when EXECUTION_MODE=live).

Defaults to Alpaca's paper-trading endpoint. The local Portfolio ledger is
still updated on every fill so the trade journal stays complete.
"""

from __future__ import annotations

import time
from typing import Callable

import requests

from ..portfolio import Portfolio
from .base import Fill


class AlpacaBroker:
    name = "alpaca"

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        base_url: str,
        portfolio: Portfolio,
        price_fn: Callable[[str], float],
    ):
        if not api_key or not secret_key:
            raise ValueError(
                "EXECUTION_MODE=live requires ALPACA_API_KEY and ALPACA_SECRET_KEY"
            )
        self.base_url = base_url.rstrip("/")
        self.portfolio = portfolio
        self.price_fn = price_fn
        self.session = requests.Session()
        self.session.headers.update(
            {
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": secret_key,
            }
        )

    def _request(self, method: str, path: str, **kwargs) -> dict:
        resp = self.session.request(
            method, f"{self.base_url}{path}", timeout=30, **kwargs
        )
        resp.raise_for_status()
        return resp.json()

    def execute_order(
        self, symbol: str, side: str, qty: float, rationale: str
    ) -> Fill:
        symbol = symbol.upper()
        order = self._request(
            "POST",
            "/v2/orders",
            json={
                "symbol": symbol,
                "qty": str(qty),
                "side": side,
                "type": "market",
                "time_in_force": "day",
            },
        )

        # Poll briefly for the fill so we can report a real price.
        fill_price = None
        for _ in range(10):
            status = self._request("GET", f"/v2/orders/{order['id']}")
            if status.get("status") == "filled":
                fill_price = float(status["filled_avg_price"])
                break
            time.sleep(1)
        if fill_price is None:
            # Market closed or slow fill — record at the last known price and
            # let Alpaca's ledger remain authoritative for the actual fill.
            fill_price = self.price_fn(symbol)

        self.portfolio.apply_fill(symbol, side, qty, fill_price, rationale)
        return Fill(
            symbol=symbol,
            side=side,
            qty=qty,
            price=fill_price,
            value=qty * fill_price,
        )
