"""Telegram bot — control JARVIS from your phone.

Mirrors the web chat: send a message to talk to the agent, approve orders
with inline buttons, and run quick commands (/portfolio, /briefing, /reset).
Uses the Telegram Bot API over long-polling (no public webhook needed).

Run with:  python -m jarvis telegram
Requires TELEGRAM_BOT_TOKEN (from @BotFather). TELEGRAM_CHAT_ID restricts the
bot to one chat; on first /start it prints the chat id to whitelist.
"""

from __future__ import annotations

import threading
import time
import uuid

import requests

TELEGRAM_LIMIT = 4096
HELP_TEXT = (
    "🤖 *JARVIS* — your AI investment agent.\n\n"
    "Just send a message to chat (e.g. _\"analyze NVDA\"_).\n\n"
    "*Commands*\n"
    "/portfolio — holdings & P&L (no AI call)\n"
    "/briefing — daily macro + portfolio briefing\n"
    "/reset — start a fresh conversation\n"
    "/help — this message"
)


# ---------- pure helpers (unit-tested) ----------

def chunk_text(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Split a long message into Telegram-sized chunks on line boundaries."""
    text = text or ""
    if len(text) <= limit:
        return [text] if text else [""]
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:  # a single very long line
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    return chunks


def approval_keyboard(req_id: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": f"approve:{req_id}"},
                {"text": "❌ Deny", "callback_data": f"deny:{req_id}"},
            ]
        ]
    }


def format_order(order: dict) -> str:
    return (
        f"🔔 *Order approval needed*\n\n"
        f"*{order['side'].upper()} {order['qty']} {order['symbol']}*\n"
        f"Est. price: ${order['est_price']:,.2f}\n"
        f"Est. value: ${order['est_value']:,.2f}\n"
        f"Conviction: {order['conviction']}\n\n"
        f"_{order['rationale']}_"
    )


def format_portfolio(snap: dict) -> str:
    lines = [
        f"💼 *Equity:* ${snap['equity']:,.2f}   *Cash:* ${snap['cash']:,.2f}",
        f"Trades today: {snap['trades_today']}",
        "",
    ]
    if not snap["positions"]:
        lines.append("_No open positions._")
    for p in snap["positions"]:
        arrow = "🟢" if p["unrealized_pnl"] >= 0 else "🔴"
        lines.append(
            f"{arrow} *{p['symbol']}* {p['qty']} @ ${p['price']:,.2f} "
            f"({p['unrealized_pnl_pct']:+.1f}%)"
        )
    return "\n".join(lines)


def parse_callback(data: str) -> tuple[str, str]:
    """'approve:abc' -> ('approve', 'abc')."""
    action, _, req_id = (data or "").partition(":")
    return action, req_id


# ---------- HTTP client ----------

class TelegramClient:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"

    def _call(self, method: str, **params):
        resp = requests.post(f"{self.base}/{method}", json=params, timeout=70)
        resp.raise_for_status()
        return resp.json().get("result")

    def get_updates(self, offset: int, timeout: int = 30):
        try:
            resp = requests.get(
                f"{self.base}/getUpdates",
                params={"offset": offset, "timeout": timeout},
                timeout=timeout + 10,
            )
            resp.raise_for_status()
            return resp.json().get("result", [])
        except requests.RequestException:
            return []

    def send_message(self, chat_id, text, reply_markup=None) -> int | None:
        msg = self._call(
            "sendMessage",
            chat_id=chat_id,
            text=text or "…",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
        return msg.get("message_id") if msg else None

    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        try:
            self._call(
                "editMessageText",
                chat_id=chat_id,
                message_id=message_id,
                text=text or "…",
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
        except requests.RequestException:
            pass  # edits can fail (unchanged text, rate limit) — non-fatal

    def answer_callback(self, callback_query_id, text=""):
        try:
            self._call("answerCallbackQuery", callback_query_id=callback_query_id, text=text)
        except requests.RequestException:
            pass


# ---------- bot ----------

class TelegramBot:
    def __init__(self, settings, broker_factory):
        self.settings = settings
        self.client = TelegramClient(settings.telegram_bot_token)
        self.allowed_chat = str(settings.telegram_chat_id) if settings.telegram_chat_id else None
        self._pending: dict[str, dict] = {}  # req_id -> {event, decision, chat_id}
        self._lock = threading.Lock()
        self._busy = threading.Lock()
        self._build_agent = lambda: self._make_agent(broker_factory)

    def _make_agent(self, broker_factory):
        from .agent import InvestmentAgent
        from .config import settings
        from .memory import Journal
        from .portfolio import Portfolio
        from .risk import RiskManager

        portfolio = Portfolio(
            settings.data_dir / "portfolio.json",
            starting_cash=settings.paper_starting_cash,
        )
        broker = broker_factory(portfolio)
        return InvestmentAgent(
            settings,
            portfolio,
            broker,
            RiskManager(settings.risk),
            Journal(settings.data_dir),
            approve_fn=self._approve,
            history_path=settings.data_dir / "chat_history.json",
        )

    # ---------- approval bridge ----------

    def _approve(self, order: dict) -> bool:
        req_id = uuid.uuid4().hex[:8]
        event = threading.Event()
        with self._lock:
            self._pending[req_id] = {"event": event, "decision": None}
        self.client.send_message(
            self._active_chat, format_order(order), reply_markup=approval_keyboard(req_id)
        )
        decided = event.wait(timeout=300)
        with self._lock:
            entry = self._pending.pop(req_id, {})
        return bool(decided and entry.get("decision"))

    def _resolve(self, req_id: str, approve: bool) -> bool:
        with self._lock:
            entry = self._pending.get(req_id)
            if not entry:
                return False
            entry["decision"] = approve
        entry["event"].set()
        return True

    # ---------- handlers ----------

    def _allowed(self, chat_id) -> bool:
        if self.allowed_chat is None:
            return True  # open until a chat id is configured
        return str(chat_id) == self.allowed_chat

    def _handle_text(self, chat_id, text: str):
        cmd = text.strip().lower()
        if cmd in ("/start", "/help"):
            self.client.send_message(chat_id, HELP_TEXT)
            if self.allowed_chat is None:
                self.client.send_message(
                    chat_id,
                    f"Chat id `{chat_id}` — set TELEGRAM_CHAT_ID to this to lock the bot.",
                )
            return
        if cmd == "/portfolio":
            from .tools import market_data

            snap = self.agent.portfolio.snapshot(market_data.last_price)
            snap["trades_today"] = self.agent.portfolio.trades_today()
            self.client.send_message(chat_id, format_portfolio(snap))
            return
        if cmd == "/reset":
            self.agent.reset()
            self.client.send_message(chat_id, "🧹 Conversation reset.")
            return

        prompt = text
        if cmd == "/briefing":
            from .prompts import BRIEFING_PROMPT

            prompt = BRIEFING_PROMPT

        if not self._busy.acquire(blocking=False):
            self.client.send_message(chat_id, "⏳ Still working on the previous request…")
            return
        threading.Thread(
            target=self._run_turn, args=(chat_id, prompt), daemon=True
        ).start()

    def _run_turn(self, chat_id, prompt: str):
        self._active_chat = chat_id
        msg_id = self.client.send_message(chat_id, "💭 Thinking…")
        buffer = {"text": ""}
        last_edit = [time.time()]

        def on_text(t: str):
            buffer["text"] += t
            now = time.time()
            if now - last_edit[0] > 1.5 and buffer["text"].strip():
                last_edit[0] = now
                self.client.edit_message(chat_id, msg_id, buffer["text"][-TELEGRAM_LIMIT:])

        try:
            self.agent.run_turn(prompt, on_text)
            final = buffer["text"].strip() or "_(no response)_"
            chunks = chunk_text(final)
            self.client.edit_message(chat_id, msg_id, chunks[0])
            for extra in chunks[1:]:
                self.client.send_message(chat_id, extra)
        except Exception as exc:
            self.client.edit_message(chat_id, msg_id, f"⚠️ Error: {exc}")
        finally:
            self._busy.release()

    def _handle_callback(self, cb):
        data = cb.get("data", "")
        action, req_id = parse_callback(data)
        approved = action == "approve"
        ok = self._resolve(req_id, approved)
        self.client.answer_callback(
            cb["id"], "Approved ✅" if approved else "Denied ❌" if ok else "Expired"
        )
        msg = cb.get("message", {})
        if ok and msg:
            verdict = "✅ *Approved*" if approved else "❌ *Denied*"
            self.client.edit_message(
                msg["chat"]["id"], msg["message_id"], msg.get("text", "") + f"\n\n{verdict}"
            )

    # ---------- loop ----------

    def run(self):
        self.agent = self._build_agent()
        self._active_chat = self.allowed_chat
        print(
            f"Telegram bot running ({self.agent.provider}:{self.agent.model}). "
            "Press Ctrl-C to stop."
        )
        offset = 0
        while True:
            try:
                updates = self.client.get_updates(offset)
            except KeyboardInterrupt:
                print("\nStopped.")
                return
            for update in updates:
                offset = update["update_id"] + 1
                if "callback_query" in update:
                    cb = update["callback_query"]
                    chat_id = cb.get("message", {}).get("chat", {}).get("id")
                    if self._allowed(chat_id):
                        self._handle_callback(cb)
                    continue
                message = update.get("message") or {}
                text = message.get("text")
                chat_id = message.get("chat", {}).get("id")
                if not text or chat_id is None:
                    continue
                if not self._allowed(chat_id):
                    self.client.send_message(chat_id, "🚫 Not authorized.")
                    continue
                self._active_chat = chat_id
                try:
                    self._handle_text(chat_id, text)
                except Exception as exc:
                    self.client.send_message(chat_id, f"⚠️ {exc}")
