import pytest

from jarvis.brokers.paper import PaperBroker
from jarvis.portfolio import Portfolio
from jarvis.stops import StopBook, StopEngine


@pytest.fixture
def book(tmp_path):
    return StopBook(tmp_path / "stops.json")


def test_stop_loss_triggers(book):
    book.set("NVDA", stop_loss_pct=10.0)
    assert book.evaluate("NVDA", avg_cost=100.0, price=89.0) is not None
    assert book.evaluate("NVDA", avg_cost=100.0, price=95.0) is None


def test_take_profit_triggers(book):
    book.set("NVDA", take_profit_pct=20.0)
    assert book.evaluate("NVDA", avg_cost=100.0, price=121.0) is not None
    assert book.evaluate("NVDA", avg_cost=100.0, price=115.0) is None


def test_trailing_stop_tracks_peak(book):
    book.set("NVDA", trailing_stop_pct=10.0)
    # Climb to 150 (sets HWM), no trigger.
    assert book.evaluate("NVDA", avg_cost=100.0, price=150.0) is None
    # Pull back 5% from peak — still safe.
    assert book.evaluate("NVDA", avg_cost=100.0, price=143.0) is None
    # Pull back >10% from the 150 peak — trigger.
    assert book.evaluate("NVDA", avg_cost=100.0, price=134.0) is not None


def test_persistence(tmp_path):
    p = tmp_path / "stops.json"
    StopBook(p).set("AAPL", stop_loss_pct=8.0)
    assert "AAPL" in StopBook(p).all()


def test_engine_executes_exit(tmp_path):
    portfolio = Portfolio(tmp_path / "p.json", starting_cash=100_000.0)
    portfolio.apply_fill("NVDA", "buy", 100, 100.0)
    book = StopBook(tmp_path / "stops.json")
    book.set("NVDA", stop_loss_pct=10.0)

    price = 85.0  # 15% below cost -> stop-loss
    broker = PaperBroker(portfolio, lambda s: price)
    exits = StopEngine(book, portfolio, broker, lambda s: price).run()

    assert len(exits) == 1
    assert exits[0]["symbol"] == "NVDA"
    assert "NVDA" not in portfolio.positions  # fully exited
    assert "NVDA" not in book.all()  # stop cleared after firing


def test_engine_noop_when_safe(tmp_path):
    portfolio = Portfolio(tmp_path / "p.json", starting_cash=100_000.0)
    portfolio.apply_fill("NVDA", "buy", 100, 100.0)
    book = StopBook(tmp_path / "stops.json")
    book.set("NVDA", stop_loss_pct=10.0)
    broker = PaperBroker(portfolio, lambda s: 105.0)
    assert StopEngine(book, portfolio, broker, lambda s: 105.0).run() == []
    assert "NVDA" in portfolio.positions
