import pandas as pd
import pytest

from jarvis.optimize import compute_optimization


def _trending(n=500):
    idx = pd.bdate_range("2021-01-04", periods=n)
    up = [100.0 * 1.003 ** i for i in range(n // 2)]
    peak = up[-1]
    down = [peak * 0.997 ** i for i in range(n - n // 2)]
    return pd.Series(up + down, index=idx)


def test_returns_best_and_leaderboard():
    prices = _trending()
    result = compute_optimization(prices, "sma_cross", objective="sharpe", fee_bps=0.0)
    assert result["combinations_tested"] > 0
    assert "best" in result
    assert result["leaderboard"][0]["score"] == result["best"]["score"]
    # Leaderboard is sorted descending by score.
    scores = [r["score"] for r in result["leaderboard"]]
    assert scores == sorted(scores, reverse=True)


def test_only_valid_param_combos_used():
    prices = _trending()
    result = compute_optimization(prices, "sma_cross", fee_bps=0.0)
    for r in result["leaderboard"]:
        assert r["params"]["fast"] < r["params"]["slow"]


def test_objective_changes_ranking_field():
    prices = _trending()
    by_return = compute_optimization(prices, "sma_cross", objective="return", fee_bps=0.0)
    assert by_return["best"]["score"] == by_return["best"]["total_return_pct"]


def test_rejects_bad_inputs():
    prices = _trending()
    with pytest.raises(ValueError, match="Unknown strategy"):
        compute_optimization(prices, "moon")
    with pytest.raises(ValueError, match="objective"):
        compute_optimization(prices, "sma_cross", objective="luck")


def test_custom_grid_respected():
    prices = _trending()
    result = compute_optimization(
        prices, "sma_cross", grid={"fast": [10], "slow": [50]}, fee_bps=0.0
    )
    assert result["combinations_tested"] == 1
    assert result["best"]["params"] == {"fast": 10, "slow": 50}


def test_random_search_bounds_evaluations():
    prices = _trending()
    big = {"fast": [5, 10, 15, 20], "slow": [30, 60, 90, 120, 150]}
    result = compute_optimization(
        prices, "sma_cross", grid=big, method="random", max_evals=5, fee_bps=0.0
    )
    assert result["method"] == "random"
    assert result["combinations_tested"] <= 5


def test_random_search_is_deterministic_with_seed():
    prices = _trending()
    big = {"fast": [5, 10, 15, 20], "slow": [30, 60, 90, 120, 150]}
    a = compute_optimization(prices, "sma_cross", grid=big, method="random", max_evals=5, seed=1, fee_bps=0.0)
    b = compute_optimization(prices, "sma_cross", grid=big, method="random", max_evals=5, seed=1, fee_bps=0.0)
    assert a["best"]["params"] == b["best"]["params"]


def test_rejects_bad_method():
    prices = _trending()
    with pytest.raises(ValueError, match="method"):
        compute_optimization(prices, "sma_cross", method="bayesian")
