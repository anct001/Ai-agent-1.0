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
    # LLM backend: "anthropic" (Claude API) or "ollama" (local model).
    llm_provider: str = os.getenv("LLM_PROVIDER", "anthropic").lower()
    model: str = os.getenv("JARVIS_MODEL", "claude-opus-4-8")
    effort: str = os.getenv("JARVIS_EFFORT", "high")
    max_tokens: int = _env_int("JARVIS_MAX_TOKENS", 64000)

    # Local model (Ollama) settings.
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

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

    # Crypto exchange (CCXT) — used when EXECUTION_MODE=crypto.
    ccxt_exchange: str = os.getenv("CCXT_EXCHANGE", "binance")
    ccxt_api_key: str = os.getenv("CCXT_API_KEY", "")
    ccxt_secret: str = os.getenv("CCXT_SECRET", "")
    ccxt_password: str = os.getenv("CCXT_PASSWORD", "")
    ccxt_quote: str = os.getenv("CCXT_QUOTE", "USDT")
    ccxt_sandbox: bool = _env_bool("CCXT_SANDBOX", True)

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

    # Telegram bot (interactive control + alert push)
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    def __post_init__(self) -> None:
        if self.execution_mode not in ("paper", "live", "crypto"):
            raise ValueError(
                "EXECUTION_MODE must be 'paper', 'live', or 'crypto', "
                f"got {self.execution_mode!r}"
            )
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._apply_saved_llm_selection()

    # ---------- runtime-selectable LLM ----------

    @property
    def _selection_path(self) -> Path:
        return self.data_dir / "llm_selection.json"

    def _apply_saved_llm_selection(self) -> None:
        """A selection made in the dashboard/CLI persists here and overrides
        env on the next start."""
        import json

        if not self._selection_path.exists():
            return
        try:
            sel = json.loads(self._selection_path.read_text())
        except (json.JSONDecodeError, OSError):
            return
        if sel.get("provider"):
            self.llm_provider = sel["provider"]
        if sel.get("anthropic_model"):
            self.model = sel["anthropic_model"]
        if sel.get("ollama_model"):
            self.ollama_model = sel["ollama_model"]

    def select_llm(self, provider: str, model: str) -> None:
        """Switch the active backend at runtime and persist the choice."""
        import json

        provider = provider.lower()
        if provider not in ("anthropic", "ollama"):
            raise ValueError("provider must be 'anthropic' or 'ollama'")
        self.llm_provider = provider
        if provider == "ollama":
            self.ollama_model = model
        else:
            self.model = model
        self._selection_path.write_text(
            json.dumps(
                {
                    "provider": self.llm_provider,
                    "anthropic_model": self.model,
                    "ollama_model": self.ollama_model,
                }
            )
        )

    def active_model(self) -> str:
        return self.ollama_model if self.llm_provider == "ollama" else self.model


settings = Settings()
