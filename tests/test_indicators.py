import pandas as pd

from jarvis.tools import indicators as ta


def _rising(n=260, step=1.0, start=100.0):
    idx = pd.bdate_range("2023-01-02", periods=n)
    return pd.Series([start + i * step for i in range(n)], index=idx)


def test_sma_matches_manual():
    s = pd.Series([1.0, 2, 3, 4, 5])
    assert ta.sma(s, 3).iloc[-1] == 4.0  # (3+4+5)/3


def test_rsi_bounded_and_high_on_uptrend():
    r = ta.rsi(_rising())
    assert (r.dropna() >= 0).all() and (r.dropna() <= 100).all()
    assert r.iloc[-1] > 70  # monotonic rise -> overbought


def test_macd_histogram_is_line_minus_signal():
    s = _rising()
    line, signal, hist = ta.macd(s)
    assert abs(hist.iloc[-1] - (line.iloc[-1] - signal.iloc[-1])) < 1e-9


def test_bollinger_band_ordering():
    s = _rising()
    low, mid, high = ta.bollinger(s)
    assert low.iloc[-1] <= mid.iloc[-1] <= high.iloc[-1]


def test_compute_indicators_signals_on_uptrend():
    s = _rising()
    out = ta.compute_indicators(s, s + 1, s - 1)
    assert out["rsi_14"] > 70
    assert out["sma_50"] is not None and out["sma_200"] is not None
    assert "atr_14" in out
    assert any("200d SMA" in sig for sig in out["signals"])
