import math

import pandas as pd
import pytest

from jarvis.backtest import compute_backtest


def _prices(days: int = 504, daily: dict[str, float] | None = None) -> pd.DataFrame:
    """Deterministic price paths with constant daily growth rates."""
    daily = daily or {"AAA": 0.001, "BBB": 0.0005}
    idx = pd.bdate_range("2022-01-03", periods=days)
    data = {
        sym: [100.0 * (1 + g) ** i for i in range(days)] for sym, g in daily.items()
    }
    return pd.DataFrame(data, index=idx)


def test_single_asset_matches_buy_and_hold():
    prices = _prices(daily={"AAA": 0.001})
    result = compute_backtest(prices, {"AAA": 1.0}, cost_bps=0.0)
    expected = (1.001 ** (len(prices) - 1) - 1) * 100
    assert result["portfolio"]["total_return_pct"] == pytest.approx(expected, rel=1e-3)
    assert result["portfolio"]["max_drawdown_pct"] == 0.0


def test_cash_remainder_dilutes_returns():
    prices = _prices(daily={"AAA": 0.001})
    full = compute_backtest(prices, {"AAA": 1.0}, cost_bps=0.0)
    half = compute_backtest(prices, {"AAA": 0.5}, cost_bps=0.0)
    assert half["cash_weight"] == 0.5
    assert (
        half["portfolio"]["total_return_pct"]
        < full["portfolio"]["total_return_pct"]
    )


def test_costs_reduce_returns():
    prices = _prices()
    weights = {"AAA": 0.6, "BBB": 0.4}
    free = compute_backtest(prices, weights, cost_bps=0.0)
    costly = compute_backtest(prices, weights, cost_bps=50.0)
    assert (
        costly["portfolio"]["total_return_pct"]
        < free["portfolio"]["total_return_pct"]
    )


def test_overallocated_weights_are_normalized():
    prices = _prices()
    result = compute_backtest(prices, {"AAA": 0.8, "BBB": 0.8}, cost_bps=0.0)
    assert sum(result["weights"].values()) == pytest.approx(1.0)
    assert result["cash_weight"] == 0.0


def test_benchmark_comparison_and_curve():
    prices = _prices(daily={"AAA": 0.001})
    bench = _prices(daily={"SPY": 0.0005})["SPY"]
    result = compute_backtest(prices, {"AAA": 1.0}, benchmark=bench, cost_bps=0.0)
    assert result["excess_cagr_pct"] > 0
    assert result["curve"][0]["portfolio_idx"] == 100.0
    assert result["curve"][-1]["portfolio_idx"] > 100.0
    assert "benchmark_idx" in result["curve"][0]
    assert not math.isnan(result["curve"][-1]["benchmark_idx"])


def test_rejects_bad_inputs():
    prices = _prices()
    with pytest.raises(ValueError, match="rebalance"):
        compute_backtest(prices, {"AAA": 1.0}, rebalance="hourly")
    with pytest.raises(ValueError, match="positive weight"):
        compute_backtest(prices, {"AAA": 0.0})
    with pytest.raises(ValueError, match="Not enough"):
        compute_backtest(prices.head(5), {"AAA": 1.0})
