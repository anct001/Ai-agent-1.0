"""Equity-curve history: one record per day, with an S&P 500 benchmark.

Recorded opportunistically (dashboard loads, trades), deduped by date so the
file stays small. Enables the "am I beating the market?" chart.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class EquityHistory:
    def __init__(self, path: Path):
        self.path = path

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def record(
        self,
        equity: float,
        benchmark: float | None = None,
        on_date: str | None = None,
    ) -> None:
        data = self._load()
        today = on_date or datetime.now(timezone.utc).date().isoformat()
        entry = {"equity": round(equity, 2)}
        if benchmark is not None:
            entry["benchmark"] = round(benchmark, 2)
        elif today in data and "benchmark" in data[today]:
            entry["benchmark"] = data[today]["benchmark"]
        data[today] = entry  # latest snapshot of the day wins
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))

    def read(self) -> list[dict]:
        """Chronological series with both curves normalized to 100 at start."""
        data = self._load()
        if not data:
            return []
        dates = sorted(data)
        first_equity = data[dates[0]]["equity"]
        first_bench = next(
            (data[d]["benchmark"] for d in dates if data[d].get("benchmark")), None
        )
        series = []
        for d in dates:
            row = {"date": d, "equity": data[d]["equity"]}
            if first_equity:
                row["equity_idx"] = round(data[d]["equity"] / first_equity * 100, 2)
            bench = data[d].get("benchmark")
            if bench and first_bench:
                row["benchmark_idx"] = round(bench / first_bench * 100, 2)
            series.append(row)
        return series
