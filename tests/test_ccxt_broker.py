"""CCXTBroker tests with a fake exchange (no ccxt install, no network)."""

import sys
import types

import pytest

from jarvis.portfolio import Portfolio


class _FakeExchange:
    def __init__(self, creds):
        self.creds = creds
        self.sandbox = False
        self.orders = []

    def set_sandbox_mode(self, on):
        self.sandbox = on

    def fetch_ticker(self, symbol):
        return {"last": 50_000.0, "symbol": symbol}

    def create_order(self, symbol, type_, side, qty):
        self.orders.append((symbol, type_, side, qty))
        return {"average": 50_000.0, "filled": qty, "fee": {"cost": 5.0}}


@pytest.fixture
def fake_ccxt(monkeypatch):
    mod = types.ModuleType("ccxt")
    mod.binance = _FakeExchange
    monkeypatch.setitem(sys.modules, "ccxt", mod)
    return mod


def _broker(tmp_path, fake_ccxt, **kw):
    from jarvis.brokers.ccxt_broker import CCXTBroker

    portfolio = Portfolio(tmp_path / "p.json", starting_cash=1_000_000.0)
    return CCXTBroker("binance", "k", "s", portfolio, **kw), portfolio


def test_symbol_mapping(tmp_path, fake_ccxt):
    broker, _ = _broker(tmp_path, fake_ccxt, quote="USDT")
    assert broker.to_exchange_symbol("BTC-USD") == "BTC/USDT"
    assert broker.to_exchange_symbol("ETH-USD") == "ETH/USDT"
    assert broker.to_exchange_symbol("SOL/USDT") == "SOL/USDT"  # pass-through


def test_sandbox_enabled_by_default(tmp_path, fake_ccxt):
    broker, _ = _broker(tmp_path, fake_ccxt)
    assert broker.exchange.sandbox is True


def test_execute_records_fill_under_original_ticker(tmp_path, fake_ccxt):
    broker, portfolio = _broker(tmp_path, fake_ccxt, quote="USDT")
    fill = broker.execute_order("BTC-USD", "buy", 0.5, "thesis")
    # Order routed to the exchange pair...
    assert broker.exchange.orders[0][0] == "BTC/USDT"
    # ...but the ledger records the yfinance-style ticker.
    assert "BTC-USD" in portfolio.positions
    assert fill.price == 50_000.0
    assert fill.fee == 5.0


def test_unknown_exchange_rejected(tmp_path, fake_ccxt):
    from jarvis.brokers.ccxt_broker import CCXTBroker

    portfolio = Portfolio(tmp_path / "p.json", starting_cash=100.0)
    with pytest.raises(ValueError, match="Unknown CCXT exchange"):
        CCXTBroker("not_an_exchange", "k", "s", portfolio)
