"""Crypto / multi-exchange broker via CCXT (optional).

Brings Freqtrade's home turf — crypto exchanges — to JARVIS. CCXT unifies
100+ exchanges behind one API. This adapter places market orders and updates
the local ledger, mirroring the Alpaca adapter.

Safety: defaults to the exchange's **sandbox/testnet** when available. Set
CCXT_SANDBOX=false only when you truly intend to trade real funds. ccxt is an
optional dependency — install with `pip install ccxt`.
"""

from __future__ import annotations

from typing import Callable

from ..portfolio import Portfolio
from .base import Fill


class CCXTBroker:
    name = "ccxt"

    def __init__(
        self,
        exchange_id: str,
        api_key: str,
        secret: str,
        portfolio: Portfolio,
        sandbox: bool = True,
        password: str = "",
        quote: str = "USDT",
    ):
        try:
            import ccxt
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise RuntimeError(
                "Crypto trading needs the ccxt package: pip install ccxt"
            ) from exc

        if not hasattr(ccxt, exchange_id):
            raise ValueError(f"Unknown CCXT exchange {exchange_id!r}")
        creds = {"apiKey": api_key, "secret": secret, "enableRateLimit": True}
        if password:
            creds["password"] = password
        self.exchange = getattr(ccxt, exchange_id)(creds)
        if sandbox:
            try:
                self.exchange.set_sandbox_mode(True)
            except Exception:
                pass  # not all exchanges expose a sandbox
        self.portfolio = portfolio
        self.quote = quote

    def to_exchange_symbol(self, symbol: str) -> str:
        """Map a yfinance-style ticker ('BTC-USD') to an exchange pair
        ('BTC/USDT'). Pass through anything already in pair form."""
        if "/" in symbol:
            return symbol
        base = symbol.upper().replace("-USD", "").replace("USD", "")
        return f"{base}/{self.quote}"

    def last_price(self, symbol: str) -> float:
        """Live price for a symbol (yfinance-style or exchange pair)."""
        ticker = self.exchange.fetch_ticker(self.to_exchange_symbol(symbol))
        price = ticker.get("last") or ticker.get("close")
        if not price:
            raise ValueError(f"No price for {symbol!r}")
        return float(price)

    def execute_order(
        self, symbol: str, side: str, qty: float, rationale: str
    ) -> Fill:
        # Execute on the exchange pair, but record under the original ticker
        # so quotes/risk/marking stay consistent with the rest of the system.
        order = self.exchange.create_order(
            self.to_exchange_symbol(symbol), "market", side, qty
        )
        price = order.get("average") or order.get("price") or self.last_price(symbol)
        filled = order.get("filled") or qty
        fee = 0.0
        if order.get("fee") and order["fee"].get("cost"):
            fee = float(order["fee"]["cost"])
        self.portfolio.apply_fill(symbol, side, filled, float(price), rationale, fee=fee)
        return Fill(
            symbol=symbol,
            side=side,
            qty=filled,
            price=float(price),
            value=filled * float(price),
            fee=fee,
        )
