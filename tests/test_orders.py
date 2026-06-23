import pytest

from jarvis.brokers.paper import PaperBroker
from jarvis.config import RiskLimits
from jarvis.orders import OrderBook, OrderEngine
from jarvis.portfolio import Portfolio
from jarvis.risk import RiskManager


@pytest.fixture
def book(tmp_path):
    return OrderBook(tmp_path / "orders.json")


def test_trigger_logic():
    limit_buy = {"side": "buy", "trigger": "limit", "price": 100.0}
    assert OrderBook.is_triggered(limit_buy, 99.0)
    assert not OrderBook.is_triggered(limit_buy, 101.0)

    stop_buy = {"side": "buy", "trigger": "stop", "price": 100.0}
    assert OrderBook.is_triggered(stop_buy, 101.0)
    assert not OrderBook.is_triggered(stop_buy, 99.0)

    limit_sell = {"side": "sell", "trigger": "limit", "price": 100.0}
    assert OrderBook.is_triggered(limit_sell, 101.0)

    stop_sell = {"side": "sell", "trigger": "stop", "price": 100.0}
    assert OrderBook.is_triggered(stop_sell, 99.0)


def test_add_validates(book):
    with pytest.raises(ValueError):
        book.add("NVDA", "short", "limit", 100, 1)
    with pytest.raises(ValueError):
        book.add("NVDA", "buy", "trail", 100, 1)
    with pytest.raises(ValueError):
        book.add("NVDA", "buy", "limit", -1, 1)


def test_persistence_and_cancel(tmp_path):
    p = tmp_path / "orders.json"
    o = OrderBook(p).add("NVDA", "buy", "limit", 100, 5, "dip")
    assert len(OrderBook(p).all()) == 1
    assert OrderBook(p).cancel(o["id"]) is True
    assert OrderBook(p).all() == []


def _engine(tmp_path, price, starting_cash=100_000.0):
    portfolio = Portfolio(tmp_path / "p.json", starting_cash=starting_cash)
    book = OrderBook(tmp_path / "orders.json")
    broker = PaperBroker(portfolio, lambda s: price)
    risk = RiskManager(RiskLimits())
    return book, OrderEngine(book, portfolio, broker, risk, lambda s: price), portfolio


def test_limit_buy_fills_when_price_drops(tmp_path):
    book, engine, portfolio = _engine(tmp_path, price=95.0)
    book.add("NVDA", "buy", "limit", 100.0, 10, "buy the dip")
    events = engine.run()
    assert events[0]["status"] == "filled"
    assert "NVDA" in portfolio.positions
    assert book.all() == []


def test_limit_buy_waits_when_price_high(tmp_path):
    book, engine, portfolio = _engine(tmp_path, price=110.0)
    book.add("NVDA", "buy", "limit", 100.0, 10, "buy the dip")
    assert engine.run() == []
    assert "NVDA" not in portfolio.positions
    assert len(book.all()) == 1  # still resting


def test_oco_fills_one_cancels_other(tmp_path):
    # Long position, OCO bracket; price jumps to take-profit.
    portfolio = Portfolio(tmp_path / "p.json", starting_cash=100_000.0)
    portfolio.apply_fill("NVDA", "buy", 10, 100.0)
    book = OrderBook(tmp_path / "orders.json")
    book.add_oco("NVDA", 10, take_profit_price=120.0, stop_loss_price=90.0)
    assert len(book.all()) == 2

    price = 125.0  # take-profit limit-sell triggers
    broker = PaperBroker(portfolio, lambda s: price)
    engine = OrderEngine(book, portfolio, broker, RiskManager(RiskLimits()), lambda s: price)
    events = engine.run()
    filled = [e for e in events if e["status"] == "filled"]
    assert len(filled) == 1
    assert "NVDA" not in portfolio.positions  # sold the lot
    assert book.all() == []  # sibling stop-loss cancelled


def test_buy_rejected_by_risk_is_cancelled(tmp_path):
    # Order far larger than per-order limit -> risk rejects -> cancelled.
    book, engine, portfolio = _engine(tmp_path, price=95.0, starting_cash=100_000.0)
    book.add("NVDA", "buy", "limit", 100.0, 1000, "too big")  # $95k >> 10% cap
    events = engine.run()
    assert events[0]["status"] == "cancelled"
    assert "risk" in events[0]["reason"]
    assert book.all() == []
