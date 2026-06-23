"""Strategy parameter optimization (Freqtrade-style Hyperopt, lite).

Grid-searches a strategy's parameters over historical bars and ranks the
combinations by an objective (Sharpe by default), so the agent can find
settings that actually held up rather than guessing. Pure pandas over
`strategy.compute_strategy`; offline-testable.
"""

from __future__ import annotations

import itertools
import random

from .strategy import compute_strategy

# Default search spaces per strategy. Kept modest so a grid stays cheap.
PARAM_GRIDS = {
    "sma_cross": {"fast": [10, 20, 50], "slow": [50, 100, 200]},
    "rsi": {"period": [7, 14, 21], "oversold": [25, 30, 35], "overbought": [65, 70, 75]},
    "macd_cross": {"fast": [8, 12], "slow": [21, 26], "signal": [9]},
    "bollinger": {"period": [10, 20, 30], "k": [1.5, 2.0, 2.5]},
}

OBJECTIVES = {
    "sharpe": ("strategy_performance", "sharpe_ratio"),
    "return": ("strategy_performance", "total_return_pct"),
    "cagr": ("strategy_performance", "cagr_pct"),
}


def _grid(space: dict):
    keys = list(space)
    for combo in itertools.product(*(space[k] for k in keys)):
        yield dict(zip(keys, combo))


def _valid(strategy: str, params: dict) -> bool:
    if strategy in ("sma_cross", "macd_cross"):
        return params["fast"] < params["slow"]
    if strategy == "rsi":
        return params["oversold"] < params["overbought"]
    return True


def compute_optimization(
    close,
    strategy: str = "sma_cross",
    grid: dict | None = None,
    objective: str = "sharpe",
    fee_bps: float = 5.0,
    stop_loss_pct: float | None = None,
    top_n: int = 5,
    method: str = "grid",
    max_evals: int = 60,
    seed: int = 0,
) -> dict:
    if strategy not in PARAM_GRIDS:
        raise ValueError(f"Unknown strategy {strategy!r}")
    if objective not in OBJECTIVES:
        raise ValueError(f"objective must be one of {sorted(OBJECTIVES)}")
    if method not in ("grid", "random"):
        raise ValueError("method must be 'grid' or 'random'")
    grid = grid or PARAM_GRIDS[strategy]
    section, field = OBJECTIVES[objective]

    combos = [p for p in _grid(grid) if _valid(strategy, p)]
    # Random search samples the space — useful when the grid is large.
    if method == "random" and len(combos) > max_evals:
        combos = random.Random(seed).sample(combos, max_evals)

    results = []
    for params in combos:
        try:
            r = compute_strategy(
                close, strategy, params, fee_bps=fee_bps, stop_loss_pct=stop_loss_pct
            )
        except ValueError:
            continue
        results.append(
            {
                "params": params,
                "score": r[section][field],
                "total_return_pct": r["strategy_performance"]["total_return_pct"],
                "sharpe_ratio": r["strategy_performance"]["sharpe_ratio"],
                "max_drawdown_pct": r["strategy_performance"]["max_drawdown_pct"],
                "num_trades": r["num_trades"],
                "win_rate_pct": r["win_rate_pct"],
            }
        )

    if not results:
        raise ValueError("No valid parameter combinations produced a backtest")

    results.sort(key=lambda x: x["score"], reverse=True)
    return {
        "strategy": strategy,
        "objective": objective,
        "method": method,
        "combinations_tested": len(results),
        "best": results[0],
        "leaderboard": results[:top_n],
    }


def run_optimize(
    symbol: str,
    strategy: str = "sma_cross",
    period: str = "5y",
    objective: str = "sharpe",
    fee_bps: float = 5.0,
    stop_loss_pct: float | None = None,
    method: str = "grid",
) -> dict:
    """Download history and optimize. Network required."""
    if strategy not in PARAM_GRIDS:
        raise ValueError(f"Unknown strategy {strategy!r}")

    import yfinance as yf

    symbol = symbol.upper()
    hist = yf.Ticker(symbol).history(period=period)
    if hist.empty:
        raise ValueError(f"No price history for {symbol!r}")
    result = compute_optimization(
        hist["Close"], strategy, objective=objective, fee_bps=fee_bps,
        stop_loss_pct=stop_loss_pct, method=method,
    )
    result["symbol"] = symbol
    result["period"] = period
    return result
