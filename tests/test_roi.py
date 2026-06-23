from datetime import datetime, timedelta, timezone

import pytest

from jarvis.brokers.paper import PaperBroker
from jarvis.portfolio import Portfolio
from jarvis.stops import StopBook, StopEngine, roi_exit


def _days_ago(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


ROI = {0: 0.10, 5: 0.05, 20: 0.02, 60: 0.0}


def test_roi_immediate_high_target():
    # Opened today, +12% -> meets the 10% bucket.
    assert roi_exit(_days_ago(0), 100.0, 112.0, ROI) is not None
    # Opened today, +6% -> below the 10% immediate target.
    assert roi_exit(_days_ago(0), 100.0, 106.0, ROI) is None


def test_roi_decays_with_age():
    # After 25 days the bucket is the 20-day one (need only +2%).
    assert roi_exit(_days_ago(25), 100.0, 103.0, ROI) is not None
    # +1% still not enough at 25 days.
    assert roi_exit(_days_ago(25), 100.0, 101.0, ROI) is None


def test_roi_any_profit_after_long_hold():
    assert roi_exit(_days_ago(70), 100.0, 100.5, ROI) is not None
    # A loss never triggers ROI.
    assert roi_exit(_days_ago(70), 100.0, 99.0, ROI) is None


def test_roi_disabled_when_empty():
    assert roi_exit(_days_ago(70), 100.0, 200.0, {}) is None


def test_roi_handles_string_keys_from_json():
    table = {"0": 0.1, "60": 0.0}
    assert roi_exit(_days_ago(70), 100.0, 101.0, table) is not None


def test_engine_applies_roi_to_all_positions(tmp_path):
    portfolio = Portfolio(tmp_path / "p.json", starting_cash=100_000.0)
    portfolio.apply_fill("NVDA", "buy", 10, 100.0)
    # Backdate the open so the 0-day +10% bucket applies cleanly.
    portfolio.positions["NVDA"].opened_at = _days_ago(1)

    book = StopBook(tmp_path / "stops.json")  # no stop set for NVDA
    price = 115.0  # +15% -> ROI exit even without a stop order
    broker = PaperBroker(portfolio, lambda s: price)
    engine = StopEngine(book, portfolio, broker, lambda s: price, roi_table=ROI)
    exits = engine.run()

    assert len(exits) == 1
    assert "ROI" in exits[0]["reason"]
    assert "NVDA" not in portfolio.positions


def test_engine_no_roi_table_ignores_stopless_position(tmp_path):
    portfolio = Portfolio(tmp_path / "p.json", starting_cash=100_000.0)
    portfolio.apply_fill("NVDA", "buy", 10, 100.0)
    book = StopBook(tmp_path / "stops.json")
    broker = PaperBroker(portfolio, lambda s: 200.0)
    engine = StopEngine(book, portfolio, broker, lambda s: 200.0)  # roi_table empty
    assert engine.run() == []
    assert "NVDA" in portfolio.positions
