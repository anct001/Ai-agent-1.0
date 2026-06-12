import pytest

from jarvis.config import RiskLimits
from jarvis.portfolio import Portfolio
from jarvis.risk import RiskManager


@pytest.fixture
def portfolio(tmp_path):
    return Portfolio(tmp_path / "portfolio.json", starting_cash=100_000.0)


@pytest.fixture
def risk():
    return RiskManager(
        RiskLimits(
            max_order_pct=0.10,
            max_position_pct=0.20,
            min_cash_pct=0.05,
            max_orders_per_day=3,
        )
    )


def _validate(risk, portfolio, symbol="NVDA", side="buy", qty=10, price=100.0):
    equity = portfolio.equity(lambda s: price)
    return risk.validate(portfolio, symbol, side, qty, price, equity)


def test_approves_reasonable_order(risk, portfolio):
    check = _validate(risk, portfolio, qty=50, price=100.0)  # $5k of $100k
    assert check.approved


def test_rejects_oversized_order(risk, portfolio):
    check = _validate(risk, portfolio, qty=150, price=100.0)  # $15k > 10%
    assert not check.approved
    assert "per-order limit" in check.reason


def test_rejects_position_concentration(risk, portfolio):
    # Build 15% position via two orders, then push past the 20% cap.
    portfolio.apply_fill("NVDA", "buy", 80, 100.0)
    portfolio.apply_fill("NVDA", "buy", 70, 100.0)
    check = _validate(risk, portfolio, qty=60, price=100.0)  # would be 21%
    assert not check.approved
    assert "single-position limit" in check.reason


def test_rejects_cash_floor_breach(tmp_path, risk):
    portfolio = Portfolio(tmp_path / "p.json", starting_cash=100_000.0)
    portfolio.cash = 6_000.0  # equity dominated by positions
    portfolio.apply_fill("AAPL", "buy", 10, 100.0)  # cash now 5,000
    equity = 100_000.0
    check = risk.validate(portfolio, "MSFT", "buy", 30, 100.0, equity)
    assert not check.approved
    assert "cash reserve" in check.reason


def test_rejects_overselling(risk, portfolio):
    check = _validate(risk, portfolio, side="sell", qty=5)
    assert not check.approved
    assert "Cannot sell" in check.reason


def test_allows_full_exit(risk, portfolio):
    portfolio.apply_fill("NVDA", "buy", 50, 100.0)
    check = _validate(risk, portfolio, side="sell", qty=50)
    assert check.approved


def test_daily_order_limit(risk, portfolio):
    for _ in range(3):
        portfolio.apply_fill("AAPL", "buy", 1, 100.0)
    check = _validate(risk, portfolio, qty=1)
    assert not check.approved
    assert "Daily order limit" in check.reason


def test_rejects_garbage_inputs(risk, portfolio):
    assert not _validate(risk, portfolio, side="short").approved
    assert not _validate(risk, portfolio, qty=-5).approved
    assert not _validate(risk, portfolio, price=0).approved
