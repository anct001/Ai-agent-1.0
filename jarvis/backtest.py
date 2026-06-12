"""Backtesting: replay a target-weight allocation against historical prices.

The agent (or user) proposes an allocation like {"NVDA": 0.4, "MSFT": 0.3}
(remainder held as cash) and gets back CAGR, volatility, Sharpe, max
drawdown, and the comparison against a benchmark — before risking anything
forward.

`compute_backtest` is pure pandas (offline-testable); `run_backtest` wraps
it with a yfinance download.
"""

from __future__ import annotations

import math

import pandas as pd

_REBALANCE_FREQ = {"weekly": "W", "monthly": "ME", "quarterly": "QE"}
TRADING_DAYS = 252


def _metrics(curve: pd.Series) -> dict:
    returns = curve.pct_change().dropna()
    years = max(len(curve) / TRADING_DAYS, 1e-9)
    total = curve.iloc[-1] / curve.iloc[0] - 1
    cagr = (curve.iloc[-1] / curve.iloc[0]) ** (1 / years) - 1
    vol = float(returns.std()) * math.sqrt(TRADING_DAYS)
    sharpe = (cagr / vol) if vol > 1e-12 else 0.0
    drawdown = float((curve / curve.cummax() - 1).min())
    return {
        "total_return_pct": round(total * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "annualized_volatility_pct": round(vol * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(drawdown * 100, 2),
    }


def compute_backtest(
    prices: pd.DataFrame,
    weights: dict[str, float],
    benchmark: pd.Series | None = None,
    rebalance: str = "monthly",
    cost_bps: float = 5.0,
    starting_value: float = 100_000.0,
) -> dict:
    """Simulate holding `weights` of `prices` columns, rebalancing
    periodically; the unallocated remainder sits in cash at 0%.

    Each rebalance charges `cost_bps` on the traded notional (the drift
    between current and target weights).
    """
    if rebalance not in _REBALANCE_FREQ:
        raise ValueError(f"rebalance must be one of {sorted(_REBALANCE_FREQ)}")
    weights = {sym.upper(): float(w) for sym, w in weights.items() if w > 0}
    if not weights:
        raise ValueError("At least one positive weight is required")
    total_w = sum(weights.values())
    if total_w > 1.0 + 1e-9:
        # Normalize over-allocated weights instead of failing.
        weights = {s: w / total_w for s, w in weights.items()}

    prices = prices[list(weights)].dropna()
    if len(prices) < 30:
        raise ValueError("Not enough overlapping price history to backtest")

    rebalance_dates = set(
        prices.resample(_REBALANCE_FREQ[rebalance]).last().index
    )

    cash_w = max(0.0, 1.0 - sum(weights.values()))
    value = starting_value
    # Holdings in units, set at each rebalance.
    units = {s: value * w / prices[s].iloc[0] for s, w in weights.items()}
    cash = value * cash_w
    curve = []

    for date, row in prices.iterrows():
        value = cash + sum(units[s] * row[s] for s in units)
        if date in rebalance_dates:
            # Traded notional = sum of |current - target| exposures.
            traded = abs(cash - value * cash_w)
            for s, w in weights.items():
                traded += abs(units[s] * row[s] - value * w)
            value -= (traded / 2) * cost_bps / 10_000.0
            units = {s: value * w / row[s] for s, w in weights.items()}
            cash = value * cash_w
        curve.append((date, value))

    series = pd.Series(
        [v for _, v in curve], index=[d for d, _ in curve], name="portfolio"
    )

    result = {
        "weights": weights,
        "cash_weight": round(cash_w, 4),
        "rebalance": rebalance,
        "cost_bps": cost_bps,
        "start": str(series.index[0].date()),
        "end": str(series.index[-1].date()),
        "portfolio": _metrics(series),
    }

    if benchmark is not None:
        bench = benchmark.reindex(series.index).dropna()
        if len(bench) >= 30:
            result["benchmark"] = _metrics(bench)
            result["excess_cagr_pct"] = round(
                result["portfolio"]["cagr_pct"] - result["benchmark"]["cagr_pct"], 2
            )

    # Sampled, normalized curve for charting (~120 points).
    step = max(1, len(series) // 120)
    sampled = series.iloc[::step]
    bench_idx = None
    if benchmark is not None:
        b = benchmark.reindex(series.index).ffill()
        bench_idx = (b / b.iloc[0] * 100).iloc[::step]
    result["curve"] = [
        {
            "date": str(idx.date()),
            "portfolio_idx": round(val / series.iloc[0] * 100, 2),
            **(
                {"benchmark_idx": round(float(bench_idx.loc[idx]), 2)}
                if bench_idx is not None and idx in bench_idx.index
                and not math.isnan(float(bench_idx.loc[idx]))
                else {}
            ),
        }
        for idx, val in sampled.items()
    ]
    return result


def run_backtest(
    weights: dict[str, float],
    period: str = "5y",
    rebalance: str = "monthly",
    benchmark_symbol: str = "SPY",
    cost_bps: float = 5.0,
) -> dict:
    """Download history and run the backtest. Network required."""
    if not any(w > 0 for w in weights.values()) or not weights:
        raise ValueError("At least one positive weight is required")
    if rebalance not in _REBALANCE_FREQ:
        raise ValueError(f"rebalance must be one of {sorted(_REBALANCE_FREQ)}")

    import yfinance as yf

    symbols = sorted({s.upper() for s in weights}) + [benchmark_symbol.upper()]
    data = yf.download(
        symbols, period=period, auto_adjust=True, progress=False
    )["Close"]
    if isinstance(data, pd.Series):
        data = data.to_frame(symbols[0])
    missing = [s for s in weights if s.upper() not in data.columns]
    if missing:
        raise ValueError(f"No price history for: {', '.join(missing)}")

    benchmark = data.get(benchmark_symbol.upper())
    result = compute_backtest(
        data, weights, benchmark=benchmark, rebalance=rebalance, cost_bps=cost_bps
    )
    result["benchmark_symbol"] = benchmark_symbol.upper()
    result["period"] = period
    return result
