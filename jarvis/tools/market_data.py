"""Market data via yfinance (no API key required).

yfinance is imported lazily inside functions so the rest of the package
(portfolio, risk, tests) imports without it installed.
"""

from __future__ import annotations

import math
import time
from functools import lru_cache

# Quotes don't need tick-level freshness here; a short TTL keeps the
# dashboard and agent loops snappy without hammering Yahoo.
_PRICE_TTL_SECONDS = 60.0
_price_cache: dict[str, tuple[float, float]] = {}  # symbol -> (price, fetched_at)


def _yf():
    import yfinance as yf

    return yf


def _clean(value):
    """Replace NaN/inf with None so output serializes to strict JSON."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


@lru_cache(maxsize=256)
def _ticker(symbol: str):
    return _yf().Ticker(symbol)


def last_price(symbol: str) -> float:
    """Latest traded price (cached ~60s); raises if the symbol has no data."""
    symbol = symbol.upper()
    cached = _price_cache.get(symbol)
    now = time.time()
    if cached and now - cached[1] < _PRICE_TTL_SECONDS:
        return cached[0]

    t = _ticker(symbol)
    price = getattr(t.fast_info, "last_price", None)
    if not (price and price > 0):
        hist = t.history(period="5d")
        if hist.empty:
            raise ValueError(f"No market data for {symbol!r}")
        price = float(hist["Close"].iloc[-1])
    price = float(price)
    _price_cache[symbol] = (price, now)
    return price


def get_quote(symbols: list[str]) -> list[dict]:
    out = []
    for symbol in symbols:
        symbol = symbol.upper()
        try:
            t = _ticker(symbol)
            hist = t.history(period="1mo")
            if hist.empty:
                out.append({"symbol": symbol, "error": "no data"})
                continue
            close = hist["Close"]
            price = float(close.iloc[-1])
            prev = float(close.iloc[-2]) if len(close) > 1 else price
            month_ago = float(close.iloc[0])
            fi = t.fast_info
            out.append(
                {
                    "symbol": symbol,
                    "price": round(price, 4),
                    "change_1d_pct": round((price / prev - 1) * 100, 2),
                    "change_1mo_pct": round((price / month_ago - 1) * 100, 2),
                    "year_high": _clean(round(getattr(fi, "year_high", 0) or 0, 2)),
                    "year_low": _clean(round(getattr(fi, "year_low", 0) or 0, 2)),
                    "market_cap": _clean(getattr(fi, "market_cap", None)),
                }
            )
        except Exception as exc:  # network/symbol errors go back to the model
            out.append({"symbol": symbol, "error": str(exc)})
    return out


def get_price_history(symbol: str, period: str = "1y", interval: str = "1d") -> dict:
    symbol = symbol.upper()
    hist = _ticker(symbol).history(period=period, interval=interval)
    if hist.empty:
        return {"symbol": symbol, "error": "no data"}

    close = hist["Close"]
    returns = close.pct_change().dropna()
    running_max = close.cummax()
    drawdown = (close / running_max - 1).min()

    summary = {
        "symbol": symbol,
        "period": period,
        "interval": interval,
        "start": str(hist.index[0].date()),
        "end": str(hist.index[-1].date()),
        "first_close": round(float(close.iloc[0]), 4),
        "last_close": round(float(close.iloc[-1]), 4),
        "total_return_pct": round((close.iloc[-1] / close.iloc[0] - 1) * 100, 2),
        "annualized_volatility_pct": round(
            float(returns.std()) * math.sqrt(252) * 100, 2
        ),
        "max_drawdown_pct": round(float(drawdown) * 100, 2),
    }
    if len(close) >= 50:
        summary["sma_50"] = round(float(close.rolling(50).mean().iloc[-1]), 4)
    if len(close) >= 200:
        summary["sma_200"] = round(float(close.rolling(200).mean().iloc[-1]), 4)

    # Recent closes only — keep the payload token-friendly.
    tail = close.tail(20)
    summary["recent_closes"] = {
        str(idx.date()): round(float(val), 4) for idx, val in tail.items()
    }
    return summary


# Fundamental fields worth the agent's attention, mapped to friendly names.
_FUNDAMENTAL_KEYS = {
    "longName": "name",
    "sector": "sector",
    "industry": "industry",
    "marketCap": "market_cap",
    "trailingPE": "trailing_pe",
    "forwardPE": "forward_pe",
    "priceToSalesTrailing12Months": "price_to_sales",
    "enterpriseToEbitda": "ev_to_ebitda",
    "profitMargins": "profit_margin",
    "grossMargins": "gross_margin",
    "operatingMargins": "operating_margin",
    "revenueGrowth": "revenue_growth_yoy",
    "earningsGrowth": "earnings_growth_yoy",
    "freeCashflow": "free_cash_flow",
    "totalCash": "total_cash",
    "totalDebt": "total_debt",
    "debtToEquity": "debt_to_equity",
    "returnOnEquity": "return_on_equity",
    "beta": "beta",
    "dividendYield": "dividend_yield",
    "heldPercentInstitutions": "institutional_ownership",
    "shortPercentOfFloat": "short_pct_of_float",
}


def get_sector(symbol: str) -> str:
    """Sector for a symbol, cached on disk (yfinance .info is slow)."""
    import json

    from ..config import settings

    symbol = symbol.upper()
    cache_path = settings.data_dir / "sectors.json"
    cache = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text())
        except json.JSONDecodeError:
            cache = {}
    if symbol in cache:
        return cache[symbol]
    try:
        info = _ticker(symbol).info or {}
        sector = info.get("sector") or (
            "ETF / Fund" if info.get("quoteType") in ("ETF", "MUTUALFUND") else "Other"
        )
    except Exception:
        return "Unknown"  # don't cache failures
    cache[symbol] = sector
    cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True))
    return sector


def sector_allocation(positions: list[dict]) -> dict[str, float]:
    """Aggregate position values by sector."""
    out: dict[str, float] = {}
    for pos in positions:
        sector = get_sector(pos["symbol"])
        out[sector] = round(out.get(sector, 0.0) + pos["value"], 2)
    return out


def asset_class(symbol: str) -> str:
    """Coarse asset class from the ticker / quote type."""
    symbol = symbol.upper()
    if symbol.endswith("-USD") or "/" in symbol:
        return "Crypto"
    try:
        info = _ticker(symbol).info or {}
    except Exception:
        return "Equity"
    qt = (info.get("quoteType") or "").upper()
    if qt in ("ETF", "MUTUALFUND"):
        return "ETF / Fund"
    if qt == "CRYPTOCURRENCY":
        return "Crypto"
    if info.get("sector") == "Financial Services" and "bond" in (
        info.get("longName", "").lower()
    ):
        return "Bonds"
    return "Equity"


def get_country(symbol: str) -> str:
    """Country of domicile, cached on disk (yfinance .info is slow)."""
    import json

    from ..config import settings

    symbol = symbol.upper()
    if symbol.endswith("-USD") or "/" in symbol:
        return "Global / Crypto"
    cache_path = settings.data_dir / "countries.json"
    cache = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text())
        except json.JSONDecodeError:
            cache = {}
    if symbol in cache:
        return cache[symbol]
    try:
        country = (_ticker(symbol).info or {}).get("country") or "Unknown"
    except Exception:
        return "Unknown"
    cache[symbol] = country
    cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True))
    return country


def _aggregate(positions: list[dict], classify) -> dict[str, float]:
    out: dict[str, float] = {}
    for pos in positions:
        key = classify(pos["symbol"])
        out[key] = round(out.get(key, 0.0) + pos["value"], 2)
    return out


def country_allocation(positions: list[dict]) -> dict[str, float]:
    return _aggregate(positions, get_country)


def asset_class_allocation(positions: list[dict]) -> dict[str, float]:
    return _aggregate(positions, asset_class)


def get_fundamentals(symbol: str) -> dict:
    symbol = symbol.upper()
    try:
        info = _ticker(symbol).info or {}
    except Exception as exc:
        return {"symbol": symbol, "error": str(exc)}
    if not info or info.get("regularMarketPrice") is None and "longName" not in info:
        return {"symbol": symbol, "error": "no fundamental data"}
    out = {"symbol": symbol}
    for raw_key, name in _FUNDAMENTAL_KEYS.items():
        if raw_key in info:
            out[name] = _clean(info[raw_key])
    return out
