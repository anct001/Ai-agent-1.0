"""Alerting: watches the portfolio for risk events and notifies you.

Rules (thresholds in .env):
  * position drawdown   — a holding is down more than X% from avg cost
  * portfolio drawdown  — equity is down more than X% from its peak
  * daily move          — equity moved more than X% in one day

Channels: dashboard (always), generic JSON webhook (Slack/Discord style
{"text": ...}), and SMTP email. Each alert fires at most once per day.
"""

from __future__ import annotations

import json
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from .config import Settings


def check_alerts(snapshot: dict, history: list[dict], settings: Settings) -> list[dict]:
    """Pure rule evaluation — returns a list of alert dicts (no side effects)."""
    alerts = []

    for pos in snapshot.get("positions", []):
        if pos["unrealized_pnl_pct"] <= -settings.alert_position_drawdown_pct:
            alerts.append(
                {
                    "key": f"pos_drawdown:{pos['symbol']}",
                    "severity": "warning",
                    "title": f"{pos['symbol']} down {abs(pos['unrealized_pnl_pct']):.1f}% from cost",
                    "detail": (
                        f"{pos['symbol']} at ${pos['price']:,.2f} vs avg cost "
                        f"${pos['avg_cost']:,.2f} — check the thesis invalidation."
                    ),
                }
            )

    equities = [h["equity"] for h in history]
    if equities:
        peak = max(equities + [snapshot["equity"]])
        if peak > 0:
            dd = (snapshot["equity"] / peak - 1) * 100
            if dd <= -settings.alert_portfolio_drawdown_pct:
                alerts.append(
                    {
                        "key": "portfolio_drawdown",
                        "severity": "critical",
                        "title": f"Portfolio drawdown {abs(dd):.1f}% from peak",
                        "detail": (
                            f"Equity ${snapshot['equity']:,.2f} vs peak ${peak:,.2f}. "
                            "Consider de-risking."
                        ),
                    }
                )

    today = datetime.now(timezone.utc).date().isoformat()
    prior = [h for h in history if h["date"] < today]
    if prior:
        yesterday = prior[-1]["equity"]
        if yesterday > 0:
            move = (snapshot["equity"] / yesterday - 1) * 100
            if abs(move) >= settings.alert_daily_move_pct:
                direction = "up" if move > 0 else "down"
                alerts.append(
                    {
                        "key": f"daily_move:{direction}",
                        "severity": "info" if move > 0 else "warning",
                        "title": f"Equity {direction} {abs(move):.1f}% today",
                        "detail": f"${yesterday:,.2f} → ${snapshot['equity']:,.2f}.",
                    }
                )

    return alerts


class AlertManager:
    """Dedupes (one notification per rule per day), persists recent alerts
    for the dashboard, and fans out to webhook/email."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = settings.data_dir / "alerts.json"

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {"sent": {}, "recent": []}

    def _save(self, state: dict) -> None:
        state["recent"] = state["recent"][-50:]
        self.path.write_text(json.dumps(state, indent=2))

    def process(self, snapshot: dict, history: list[dict]) -> list[dict]:
        """Evaluate rules, notify on new alerts, return today's active alerts."""
        alerts = check_alerts(snapshot, history, self.settings)
        state = self._load()
        today = datetime.now(timezone.utc).date().isoformat()
        new = []
        for alert in alerts:
            if state["sent"].get(alert["key"]) == today:
                continue
            state["sent"][alert["key"]] = today
            alert["timestamp"] = datetime.now(timezone.utc).isoformat()
            state["recent"].append(alert)
            new.append(alert)
        if new:
            self._save(state)
            self._notify(new)
        return [a for a in state["recent"] if a["timestamp"].startswith(today)]

    def recent(self) -> list[dict]:
        return list(reversed(self._load()["recent"]))

    # ---------- channels ----------

    def _notify(self, alerts: list[dict]) -> None:
        body = "\n".join(f"[{a['severity']}] {a['title']} — {a['detail']}" for a in alerts)
        if self.settings.alert_webhook_url:
            try:
                import requests

                requests.post(
                    self.settings.alert_webhook_url,
                    json={"text": f"JARVIS alerts:\n{body}"},
                    timeout=10,
                )
            except Exception:
                pass  # alerting must never crash the agent
        if self.settings.smtp_host and self.settings.alert_email_to:
            try:
                msg = EmailMessage()
                msg["Subject"] = f"JARVIS: {alerts[0]['title']}" + (
                    f" (+{len(alerts) - 1} more)" if len(alerts) > 1 else ""
                )
                msg["From"] = self.settings.smtp_user or "jarvis@localhost"
                msg["To"] = self.settings.alert_email_to
                msg.set_content(body)
                with smtplib.SMTP(
                    self.settings.smtp_host, self.settings.smtp_port, timeout=15
                ) as server:
                    server.starttls()
                    if self.settings.smtp_user:
                        server.login(self.settings.smtp_user, self.settings.smtp_password)
                    server.send_message(msg)
            except Exception:
                pass
