"""Central configuration, loaded from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is optional; plain env vars still work
    pass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


@dataclass
class RiskLimits:
    max_order_pct: float = _env_float("RISK_MAX_ORDER_PCT", 0.10)
    max_position_pct: float = _env_float("RISK_MAX_POSITION_PCT", 0.20)
    min_cash_pct: float = _env_float("RISK_MIN_CASH_PCT", 0.05)
    max_orders_per_day: int = _env_int("RISK_MAX_ORDERS_PER_DAY", 10)


@dataclass
class Settings:
    model: str = os.getenv("JARVIS_MODEL", "claude-opus-4-8")
    effort: str = os.getenv("JARVIS_EFFORT", "high")
    max_tokens: int = _env_int("JARVIS_MAX_TOKENS", 64000)

    execution_mode: str = os.getenv("EXECUTION_MODE", "paper").lower()
    paper_starting_cash: float = _env_float("PAPER_STARTING_CASH", 100_000.0)
    auto_approve: bool = _env_bool("AUTO_APPROVE", False)

    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("JARVIS_DATA_DIR", "data"))
    )
    risk: RiskLimits = field(default_factory=RiskLimits)

    alpaca_api_key: str = os.getenv("ALPACA_API_KEY", "")
    alpaca_secret_key: str = os.getenv("ALPACA_SECRET_KEY", "")
    alpaca_base_url: str = os.getenv(
        "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
    )

    # Dashboard auth: when set, every /api request must send
    # "Authorization: Bearer <token>".
    dashboard_token: str = os.getenv("JARVIS_DASHBOARD_TOKEN", "")

    # Paper-fill realism
    fill_slippage_bps: float = _env_float("FILL_SLIPPAGE_BPS", 5.0)
    commission_per_order: float = _env_float("COMMISSION_PER_ORDER", 0.0)

    # Alerts
    alert_position_drawdown_pct: float = _env_float("ALERT_POSITION_DRAWDOWN_PCT", 15.0)
    alert_portfolio_drawdown_pct: float = _env_float("ALERT_PORTFOLIO_DRAWDOWN_PCT", 10.0)
    alert_daily_move_pct: float = _env_float("ALERT_DAILY_MOVE_PCT", 5.0)
    alert_webhook_url: str = os.getenv("ALERT_WEBHOOK_URL", "")
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = _env_int("SMTP_PORT", 587)
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    alert_email_to: str = os.getenv("ALERT_EMAIL_TO", "")

    def __post_init__(self) -> None:
        if self.execution_mode not in ("paper", "live"):
            raise ValueError(
                f"EXECUTION_MODE must be 'paper' or 'live', got {self.execution_mode!r}"
            )
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
