"""Technical indicators in pure pandas (no TA-Lib dependency).

Provides the indicators a Freqtrade-style strategy reasons on — SMA/EMA,
RSI, MACD, Bollinger Bands, ATR — plus a `get_indicators` helper that
downloads history and returns the latest values with a plain-language
signal read for the agent.
"""

from __future__ import annotations

import math

import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return (100 - 100 / (1 + rs)).fillna(100)


def macd(
    s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = ema(s, fast) - ema(s, slow)
    signal_line = ema(line, signal)
    return line, signal_line, line - signal_line


def bollinger(
    s: pd.Series, n: int = 20, k: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(s, n)
    std = s.rolling(n).std()
    return mid - k * std, mid, mid + k * std


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev_close = close.shift()
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _f(value) -> float | None:
    if value is None:
        return None
    value = float(value)
    return None if math.isnan(value) or math.isinf(value) else round(value, 4)


def compute_indicators(
    close: pd.Series, high: pd.Series | None = None, low: pd.Series | None = None
) -> dict:
    """Latest indicator values plus a signal interpretation."""
    price = float(close.iloc[-1])
    macd_line, signal_line, hist = macd(close)
    bb_low, bb_mid, bb_high = bollinger(close)
    rsi_val = _f(rsi(close).iloc[-1])
    sma50 = _f(sma(close, 50).iloc[-1]) if len(close) >= 50 else None
    sma200 = _f(sma(close, 200).iloc[-1]) if len(close) >= 200 else None

    signals = []
    if rsi_val is not None:
        if rsi_val < 30:
            signals.append("RSI oversold (<30)")
        elif rsi_val > 70:
            signals.append("RSI overbought (>70)")
    if _f(hist.iloc[-1]) is not None:
        prev_hist = _f(hist.iloc[-2]) if len(hist) > 1 else None
        if prev_hist is not None:
            if hist.iloc[-2] <= 0 < hist.iloc[-1]:
                signals.append("MACD bullish crossover")
            elif hist.iloc[-2] >= 0 > hist.iloc[-1]:
                signals.append("MACD bearish crossover")
    if sma50 and sma200:
        signals.append("price above 200d SMA" if price > sma200 else "price below 200d SMA")
        signals.append("golden cross (50>200)" if sma50 > sma200 else "death cross (50<200)")
    if _f(bb_high.iloc[-1]) is not None:
        if price > bb_high.iloc[-1]:
            signals.append("above upper Bollinger band")
        elif price < bb_low.iloc[-1]:
            signals.append("below lower Bollinger band")

    out = {
        "price": round(price, 4),
        "rsi_14": rsi_val,
        "macd": _f(macd_line.iloc[-1]),
        "macd_signal": _f(signal_line.iloc[-1]),
        "macd_histogram": _f(hist.iloc[-1]),
        "sma_50": sma50,
        "sma_200": sma200,
        "bollinger_low": _f(bb_low.iloc[-1]),
        "bollinger_mid": _f(bb_mid.iloc[-1]),
        "bollinger_high": _f(bb_high.iloc[-1]),
        "signals": signals or ["no strong signal"],
    }
    if high is not None and low is not None:
        out["atr_14"] = _f(atr(high, low, close).iloc[-1])
    return out


def get_indicators(symbol: str, period: str = "1y") -> dict:
    """Download history and compute indicators. Network required."""
    import yfinance as yf

    symbol = symbol.upper()
    hist = yf.Ticker(symbol).history(period=period)
    if hist.empty or len(hist) < 30:
        return {"symbol": symbol, "error": "not enough price history"}
    result = compute_indicators(hist["Close"], hist["High"], hist["Low"])
    result["symbol"] = symbol
    result["period"] = period
    return result
