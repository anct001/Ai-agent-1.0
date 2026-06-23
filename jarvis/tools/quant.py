"""Quant research analytics: correlation, risk, and concentration.

Pure-pandas computations powering the Quant Research dashboard. The
`compute_*` functions are offline-testable; `correlation_for` adds a yfinance
download on top.
"""

from __future__ import annotations

import math

import pandas as pd

TRADING_DAYS = 252


def compute_correlation(prices: pd.DataFrame) -> dict:
    """Pairwise correlation of daily returns for the given price columns."""
    returns = prices.pct_change().dropna()
    if returns.empty or returns.shape[1] < 2:
        return {"symbols": list(prices.columns), "matrix": []}
    corr = returns.corr()
    symbols = list(corr.columns)
    matrix = [[round(float(corr.loc[a, b]), 2) for b in symbols] for a in symbols]
    return {"symbols": symbols, "matrix": matrix}


def risk_metrics(equity: list[float]) -> dict:
    """Risk stats from a daily equity series (e.g. the equity history)."""
    if not equity or len(equity) < 3:
        return {"insufficient_data": True, "points": len(equity)}
    s = pd.Series([float(x) for x in equity])
    returns = s.pct_change().dropna()
    if returns.empty:
        return {"insufficient_data": True, "points": len(equity)}

    ann_vol = float(returns.std()) * math.sqrt(TRADING_DAYS)
    ann_return = float(returns.mean()) * TRADING_DAYS
    sharpe = ann_return / ann_vol if ann_vol > 1e-12 else 0.0
    downside = returns[returns < 0]
    downside_vol = float(downside.std()) * math.sqrt(TRADING_DAYS) if len(downside) else 0.0
    sortino = ann_return / downside_vol if downside_vol > 1e-12 else 0.0
    drawdown = float((s / s.cummax() - 1).min())
    var95 = float(returns.quantile(0.05))
    cvar95 = float(returns[returns <= var95].mean()) if (returns <= var95).any() else var95

    return {
        "insufficient_data": False,
        "points": len(equity),
        "total_return_pct": round((s.iloc[-1] / s.iloc[0] - 1) * 100, 2),
        "annualized_return_pct": round(ann_return * 100, 2),
        "annualized_volatility_pct": round(ann_vol * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "max_drawdown_pct": round(drawdown * 100, 2),
        "daily_var_95_pct": round(var95 * 100, 2),
        "daily_cvar_95_pct": round(cvar95 * 100, 2),
        "best_day_pct": round(float(returns.max()) * 100, 2),
        "worst_day_pct": round(float(returns.min()) * 100, 2),
    }


def concentration(positions: list[dict]) -> dict:
    """Portfolio concentration: Herfindahl index, effective N, top weight."""
    values = [p["value"] for p in positions if p.get("value", 0) > 0]
    total = sum(values)
    if total <= 0:
        return {"holdings": 0, "hhi": 0.0, "effective_n": 0.0, "top_weight_pct": 0.0}
    weights = [v / total for v in values]
    hhi = sum(w * w for w in weights)
    return {
        "holdings": len(values),
        "hhi": round(hhi, 4),
        "effective_n": round(1 / hhi, 2) if hhi > 0 else 0.0,
        "top_weight_pct": round(max(weights) * 100, 2),
    }


def correlation_for(symbols: list[str], period: str = "1y") -> dict:
    """Download closes for symbols and compute the correlation matrix."""
    symbols = [s.upper() for s in symbols]
    if len(symbols) < 2:
        return {"symbols": symbols, "matrix": []}

    import yfinance as yf

    data = yf.download(symbols, period=period, auto_adjust=True, progress=False)["Close"]
    if isinstance(data, pd.Series):
        data = data.to_frame(symbols[0])
    data = data.dropna(how="all").dropna(axis=1, how="all")
    return compute_correlation(data)
