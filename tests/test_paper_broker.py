import pytest

from jarvis.brokers.paper import PaperBroker
from jarvis.portfolio import Portfolio


@pytest.fixture
def portfolio(tmp_path):
    return Portfolio(tmp_path / "portfolio.json", starting_cash=10_000.0)


def test_buy_slippage_fills_above_quote(portfolio):
    broker = PaperBroker(portfolio, lambda s: 100.0, slippage_bps=10.0)
    fill = broker.execute_order("NVDA", "buy", 10, "test")
    assert fill.price == pytest.approx(100.10)
    assert portfolio.positions["NVDA"].avg_cost == pytest.approx(100.10)


def test_sell_slippage_fills_below_quote(portfolio):
    broker = PaperBroker(portfolio, lambda s: 100.0, slippage_bps=10.0)
    broker.execute_order("NVDA", "buy", 10, "open")
    fill = broker.execute_order("NVDA", "sell", 10, "close")
    assert fill.price == pytest.approx(99.90)


def test_commission_reduces_cash(portfolio):
    broker = PaperBroker(portfolio, lambda s: 100.0, commission=1.50)
    broker.execute_order("AAPL", "buy", 10, "test")
    assert portfolio.cash == pytest.approx(10_000.0 - 1_000.0 - 1.50)
    assert portfolio.trades[-1]["fee"] == 1.50


def test_zero_friction_default(portfolio):
    broker = PaperBroker(portfolio, lambda s: 100.0)
    fill = broker.execute_order("MSFT", "buy", 10, "test")
    assert fill.price == 100.0
    assert fill.fee == 0.0
    assert portfolio.cash == pytest.approx(9_000.0)
