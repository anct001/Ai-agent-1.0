import pandas as pd

from jarvis.tools.quant import compute_correlation, concentration, risk_metrics


def test_correlation_perfectly_correlated():
    idx = pd.bdate_range("2023-01-02", periods=100)
    base = pd.Series([100 + i for i in range(100)], index=idx)
    df = pd.DataFrame({"A": base, "B": base * 2})  # same returns
    out = compute_correlation(df)
    assert out["symbols"] == ["A", "B"]
    assert out["matrix"][0][1] == 1.0  # perfectly correlated


def test_correlation_needs_two_columns():
    idx = pd.bdate_range("2023-01-02", periods=10)
    out = compute_correlation(pd.DataFrame({"A": range(10)}, index=idx))
    assert out["matrix"] == []


def test_risk_metrics_basic():
    equity = [100_000 * (1.001 ** i) for i in range(120)]  # steady growth
    r = risk_metrics(equity)
    assert not r["insufficient_data"]
    assert r["total_return_pct"] > 0
    assert r["annualized_volatility_pct"] >= 0
    assert r["max_drawdown_pct"] == 0.0  # monotonic up
    assert "daily_var_95_pct" in r


def test_risk_metrics_insufficient():
    assert risk_metrics([100.0])["insufficient_data"] is True
    assert risk_metrics([])["insufficient_data"] is True


def test_concentration_hhi_and_effective_n():
    positions = [
        {"symbol": "A", "value": 5000.0},
        {"symbol": "B", "value": 5000.0},
    ]
    c = concentration(positions)
    assert c["holdings"] == 2
    assert c["hhi"] == 0.5  # two equal halves
    assert c["effective_n"] == 2.0
    assert c["top_weight_pct"] == 50.0


def test_concentration_single_holding():
    c = concentration([{"symbol": "A", "value": 1000.0}])
    assert c["hhi"] == 1.0
    assert c["effective_n"] == 1.0
    assert c["top_weight_pct"] == 100.0


def test_concentration_empty():
    c = concentration([])
    assert c["holdings"] == 0
    assert c["effective_n"] == 0.0
