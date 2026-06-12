"""Investment journal — the agent's persistent memory across sessions.

Two surfaces:
  * theses:   structured investment theses with conviction and horizon
  * lessons:  free-form post-mortems and learnings the agent records
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class Journal:
    def __init__(self, data_dir: Path):
        self.theses_path = data_dir / "theses.jsonl"
        self.lessons_path = data_dir / "lessons.jsonl"
        data_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _append(path: Path, entry: dict) -> None:
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        with path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    @staticmethod
    def _read(path: Path, limit: int) -> list[dict]:
        if not path.exists():
            return []
        lines = path.read_text().strip().splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def record_thesis(
        self,
        symbol: str,
        thesis: str,
        conviction: str,
        horizon: str,
        invalidation: str,
    ) -> dict:
        entry = {
            "symbol": symbol.upper(),
            "thesis": thesis,
            "conviction": conviction,
            "horizon": horizon,
            "invalidation": invalidation,
        }
        self._append(self.theses_path, entry)
        return entry

    def record_lesson(self, lesson: str, context: str = "") -> dict:
        entry = {"lesson": lesson, "context": context}
        self._append(self.lessons_path, entry)
        return entry

    def read(self, limit: int = 20) -> dict:
        return {
            "theses": self._read(self.theses_path, limit),
            "lessons": self._read(self.lessons_path, limit),
        }

    def theses_for(self, symbol: str, limit: int = 5) -> list[dict]:
        symbol = symbol.upper()
        all_theses = self._read(self.theses_path, 1000)
        return [t for t in all_theses if t["symbol"] == symbol][-limit:]
