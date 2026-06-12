import json

import pytest

from jarvis.portfolio import Portfolio


@pytest.fixture
def portfolio(tmp_path):
    return Portfolio(tmp_path / "portfolio.json", starting_cash=10_000.0)


def test_buy_updates_cash_and_position(portfolio):
    portfolio.apply_fill("NVDA", "buy", 10, 100.0)
    assert portfolio.cash == 9_000.0
    assert portfolio.positions["NVDA"].qty == 10
    assert portfolio.positions["NVDA"].avg_cost == 100.0


def test_buy_averages_cost(portfolio):
    portfolio.apply_fill("NVDA", "buy", 10, 100.0)
    portfolio.apply_fill("NVDA", "buy", 10, 200.0)
    assert portfolio.positions["NVDA"].qty == 20
    assert portfolio.positions["NVDA"].avg_cost == 150.0


def test_sell_closes_position(portfolio):
    portfolio.apply_fill("NVDA", "buy", 10, 100.0)
    portfolio.apply_fill("NVDA", "sell", 10, 120.0)
    assert "NVDA" not in portfolio.positions
    assert portfolio.cash == 10_200.0


def test_cannot_oversell(portfolio):
    portfolio.apply_fill("NVDA", "buy", 5, 100.0)
    with pytest.raises(ValueError, match="Insufficient shares"):
        portfolio.apply_fill("NVDA", "sell", 10, 100.0)


def test_cannot_overspend(portfolio):
    with pytest.raises(ValueError, match="Insufficient cash"):
        portfolio.apply_fill("NVDA", "buy", 1000, 100.0)


def test_persistence_roundtrip(tmp_path):
    path = tmp_path / "portfolio.json"
    p1 = Portfolio(path, starting_cash=10_000.0)
    p1.apply_fill("AAPL", "buy", 4, 250.0)

    p2 = Portfolio(path, starting_cash=999.0)  # starting cash ignored on load
    assert p2.cash == 9_000.0
    assert p2.positions["AAPL"].qty == 4
    assert len(p2.trades) == 1

    saved = json.loads(path.read_text())
    assert saved["positions"]["AAPL"]["avg_cost"] == 250.0


def test_snapshot_marks_to_market(portfolio):
    portfolio.apply_fill("AAPL", "buy", 10, 100.0)
    snap = portfolio.snapshot(lambda s: 110.0)
    assert snap["equity"] == 9_000.0 + 1_100.0
    assert snap["positions"][0]["unrealized_pnl"] == 100.0
