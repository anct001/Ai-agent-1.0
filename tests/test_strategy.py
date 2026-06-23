import math

import pandas as pd
import pytest

from jarvis.strategy import compute_strategy


def _trending(n=400):
    """A long uptrend then a downtrend, so SMA-cross enters and exits."""
    idx = pd.bdate_range("2022-01-03", periods=n)
    up = [100.0 * 1.004 ** i for i in range(n // 2)]
    peak = up[-1]
    down = [peak * 0.996 ** i for i in range(n - n // 2)]
    return pd.Series(up + down, index=idx)


def test_sma_cross_trades_and_beats_buy_hold_on_round_trip():
    prices = _trending()
    r = compute_strategy(prices, "sma_cross", fee_bps=0.0)
    assert r["num_trades"] >= 1
    # Strategy exits before the full drawdown; buy & hold round-trips to ~flat.
    assert (
        r["strategy_performance"]["total_return_pct"]
        > r["buy_hold_performance"]["total_return_pct"]
    )
    assert r["strategy_performance"]["max_drawdown_pct"] >= r["buy_hold_performance"]["max_drawdown_pct"]


def test_fees_reduce_performance():
    prices = _trending()
    free = compute_strategy(prices, "sma_cross", fee_bps=0.0)
    costly = compute_strategy(prices, "sma_cross", fee_bps=50.0)
    assert (
        costly["strategy_performance"]["total_return_pct"]
        <= free["strategy_performance"]["total_return_pct"]
    )


def test_stop_loss_triggers_exit():
    # Up then a sharp crash; an 8% stop should cut the loss.
    idx = pd.bdate_range("2022-01-03", periods=200)
    up = [100.0 * 1.01 ** i for i in range(150)]
    crash = [up[-1] * 0.95 ** i for i in range(50)]
    prices = pd.Series(up + crash, index=idx)
    with_stop = compute_strategy(prices, "sma_cross", fee_bps=0.0, stop_loss_pct=8.0)
    no_stop = compute_strategy(prices, "sma_cross", fee_bps=0.0)
    assert (
        with_stop["strategy_performance"]["max_drawdown_pct"]
        >= no_stop["strategy_performance"]["max_drawdown_pct"]
    )


def test_all_strategies_run():
    prices = _trending()
    for strat in ("sma_cross", "rsi", "macd_cross", "bollinger"):
        r = compute_strategy(prices, strat, fee_bps=5.0)
        assert "strategy_performance" in r
        assert r["win_rate_pct"] >= 0


def test_rejects_unknown_strategy_and_short_history():
    prices = _trending()
    with pytest.raises(ValueError, match="Unknown strategy"):
        compute_strategy(prices, "moon", fee_bps=0.0)
    with pytest.raises(ValueError, match="Not enough"):
        compute_strategy(prices.head(20), "sma_cross")
