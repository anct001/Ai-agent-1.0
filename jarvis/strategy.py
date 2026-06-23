"""Signal-level strategy backtester (Freqtrade-style).

Unlike `backtest.py` (which replays a fixed target-weight allocation), this
runs a rule-based long/flat strategy driven by technical indicators over
historical bars, with trading fees and an optional stop-loss, and reports
per-trade statistics plus the comparison against buy-and-hold.

Strategies (all long-only; position is 1 when in-market, 0 when flat):
  * sma_cross      — long while fast SMA > slow SMA
  * rsi            — long below oversold, exit above overbought (mean reversion)
  * macd_cross     — long while MACD line > signal line
  * bollinger      — long below lower band, exit above middle band

`compute_strategy` is pure pandas (offline-testable); `run_strategy` wraps it
with a yfinance download.
"""

from __future__ import annotations

import math

import pandas as pd

from .tools import indicators as ta

TRADING_DAYS = 252

STRATEGIES = {
    "sma_cross": {"fast": 20, "slow": 50},
    "rsi": {"period": 14, "oversold": 30, "overbought": 70},
    "macd_cross": {"fast": 12, "slow": 26, "signal": 9},
    "bollinger": {"period": 20, "k": 2.0},
}


def _positions(close: pd.Series, strategy: str, params: dict) -> pd.Series:
    """A 0/1 in-market series for the strategy (pre-shift, no lookahead fix)."""
    if strategy == "sma_cross":
        fast = ta.sma(close, params["fast"])
        slow = ta.sma(close, params["slow"])
        return (fast > slow).astype(float)

    if strategy == "macd_cross":
        line, signal, _ = ta.macd(
            close, params["fast"], params["slow"], params["signal"]
        )
        return (line > signal).astype(float)

    if strategy == "rsi":
        r = ta.rsi(close, params["period"])
        pos, holding = [], 0
        for val in r:
            if math.isnan(val):
                pos.append(0)
                continue
            if holding == 0 and val < params["oversold"]:
                holding = 1
            elif holding == 1 and val > params["overbought"]:
                holding = 0
            pos.append(holding)
        return pd.Series(pos, index=close.index, dtype=float)

    if strategy == "bollinger":
        low, mid, _ = ta.bollinger(close, params["period"], params["k"])
        pos, holding = [], 0
        for i in range(len(close)):
            price = close.iloc[i]
            lo, md = low.iloc[i], mid.iloc[i]
            if math.isnan(lo):
                pos.append(0)
                continue
            if holding == 0 and price < lo:
                holding = 1
            elif holding == 1 and price > md:
                holding = 0
            pos.append(holding)
        return pd.Series(pos, index=close.index, dtype=float)

    raise ValueError(f"Unknown strategy {strategy!r}; choose from {sorted(STRATEGIES)}")


def _metrics(curve: pd.Series) -> dict:
    returns = curve.pct_change().dropna()
    years = max(len(curve) / TRADING_DAYS, 1e-9)
    cagr = (curve.iloc[-1] / curve.iloc[0]) ** (1 / years) - 1
    vol = float(returns.std()) * math.sqrt(TRADING_DAYS)
    return {
        "total_return_pct": round((curve.iloc[-1] / curve.iloc[0] - 1) * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "sharpe_ratio": round(cagr / vol, 2) if vol > 1e-12 else 0.0,
        "max_drawdown_pct": round(float((curve / curve.cummax() - 1).min()) * 100, 2),
    }


def compute_strategy(
    close: pd.Series,
    strategy: str = "sma_cross",
    params: dict | None = None,
    fee_bps: float = 5.0,
    stop_loss_pct: float | None = None,
    starting_value: float = 100_000.0,
) -> dict:
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy {strategy!r}; choose from {sorted(STRATEGIES)}")
    params = {**STRATEGIES[strategy], **(params or {})}
    close = close.dropna()
    if len(close) < 60:
        raise ValueError("Not enough price history to backtest a strategy")

    # Signal acts next bar — shift to avoid lookahead.
    target = _positions(close, strategy, params).shift(1).fillna(0)
    returns = close.pct_change().fillna(0)
    fee = fee_bps / 10_000.0

    equity = starting_value
    position = 0  # 0 flat, 1 long
    entry_price = 0.0
    curve, trades = [], []

    for i in range(len(close)):
        date, price, want = close.index[i], close.iloc[i], target.iloc[i]

        # Stop-loss check while long (intrabar approximation on close).
        if position == 1 and stop_loss_pct is not None:
            if price <= entry_price * (1 - stop_loss_pct / 100.0):
                want = 0  # force exit

        if want == 1 and position == 0:  # enter
            equity *= 1 - fee
            position, entry_price = 1, price
            trades.append({"entry_date": str(date.date()), "entry": round(price, 4)})
        elif want == 0 and position == 1:  # exit
            equity *= 1 - fee
            position = 0
            t = trades[-1]
            t["exit_date"] = str(date.date())
            t["exit"] = round(price, 4)
            t["return_pct"] = round((price / t["entry"] - 1) * 100, 2)

        if position == 1:
            equity *= 1 + returns.iloc[i]
        curve.append(equity)

    series = pd.Series(curve, index=close.index)
    closed = [t for t in trades if "return_pct" in t]
    wins = [t for t in closed if t["return_pct"] > 0]
    buy_hold = close / close.iloc[0] * starting_value

    return {
        "strategy": strategy,
        "params": params,
        "fee_bps": fee_bps,
        "stop_loss_pct": stop_loss_pct,
        "start": str(close.index[0].date()),
        "end": str(close.index[-1].date()),
        "num_trades": len(closed),
        "open_trade": position == 1,
        "win_rate_pct": round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
        "avg_win_pct": round(sum(t["return_pct"] for t in wins) / len(wins), 2)
        if wins
        else 0.0,
        "avg_loss_pct": round(
            sum(t["return_pct"] for t in closed if t["return_pct"] <= 0)
            / max(len(closed) - len(wins), 1),
            2,
        )
        if closed
        else 0.0,
        "strategy_performance": _metrics(series),
        "buy_hold_performance": _metrics(buy_hold),
        "recent_trades": closed[-10:],
        "_curve": series,  # for the UI; callers may drop it
    }


def run_strategy(
    symbol: str,
    strategy: str = "sma_cross",
    period: str = "5y",
    params: dict | None = None,
    fee_bps: float = 5.0,
    stop_loss_pct: float | None = None,
) -> dict:
    """Download history and backtest the strategy. Network required."""
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy {strategy!r}; choose from {sorted(STRATEGIES)}")

    import yfinance as yf

    symbol = symbol.upper()
    hist = yf.Ticker(symbol).history(period=period)
    if hist.empty:
        raise ValueError(f"No price history for {symbol!r}")
    result = compute_strategy(
        hist["Close"], strategy, params, fee_bps, stop_loss_pct
    )
    result["symbol"] = symbol
    result["period"] = period

    series = result.pop("_curve")
    bh = (hist["Close"] / hist["Close"].iloc[0] * 100)
    step = max(1, len(series) // 120)
    result["curve"] = [
        {
            "date": str(idx.date()),
            "strategy_idx": round(val / series.iloc[0] * 100, 2),
            "buy_hold_idx": round(float(bh.iloc[i]), 2),
        }
        for i, (idx, val) in enumerate(series.items())
        if i % step == 0
    ]
    return result
