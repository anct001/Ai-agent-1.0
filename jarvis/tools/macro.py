"""Macro / economic-trend snapshot built from liquid market proxies.

These instruments price macro expectations in real time, so the agent can
read the macro regime without any paid data feed:

  rates      ^TNX (US 10Y yield), ^IRX (13-week T-bill)
  risk       ^VIX (equity vol), HYG (high-yield credit)
  growth     ^GSPC (S&P 500), ^IXIC (Nasdaq), IWM (small caps)
  inflation  CL=F (WTI crude), GC=F (gold), DX=F (dollar index)
  liquidity  BTC-USD (risk-appetite barometer)
"""

from __future__ import annotations

_INDICATORS = {
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq Composite",
    "IWM": "Russell 2000 ETF (small caps)",
    "^TNX": "US 10Y Treasury yield (%)",
    "^IRX": "US 13-week T-bill yield (%)",
    "^VIX": "CBOE Volatility Index",
    "HYG": "High-yield corporate bond ETF",
    "DX=F": "US Dollar Index futures",
    "CL=F": "WTI Crude Oil futures",
    "GC=F": "Gold futures",
    "BTC-USD": "Bitcoin",
}


def get_macro_snapshot() -> dict:
    import yfinance as yf

    snapshot = {}
    for symbol, label in _INDICATORS.items():
        try:
            hist = yf.Ticker(symbol).history(period="6mo")
            if hist.empty:
                snapshot[label] = {"error": "no data"}
                continue
            close = hist["Close"]
            last = float(close.iloc[-1])
            prev = float(close.iloc[-2]) if len(close) > 1 else last
            month_idx = max(0, len(close) - 22)
            month_ago = float(close.iloc[month_idx])
            first = float(close.iloc[0])
            snapshot[label] = {
                "last": round(last, 2),
                "change_1d_pct": round((last / prev - 1) * 100, 2),
                "change_1mo_pct": round((last / month_ago - 1) * 100, 2),
                "change_6mo_pct": round((last / first - 1) * 100, 2),
            }
        except Exception as exc:
            snapshot[label] = {"error": str(exc)}

    # Yield-curve read: 10Y minus 3M as a recession-signal proxy.
    try:
        ten_year = snapshot["US 10Y Treasury yield (%)"]["last"]
        three_month = snapshot["US 13-week T-bill yield (%)"]["last"]
        snapshot["yield_curve_10y_minus_3m"] = round(ten_year - three_month, 2)
    except (KeyError, TypeError):
        pass

    return snapshot
