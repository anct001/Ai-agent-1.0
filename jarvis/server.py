"""Web dashboard server for JARVIS.

    python -m jarvis dashboard          # http://127.0.0.1:8000

Endpoints:
    GET  /                      dashboard SPA
    GET  /api/portfolio         snapshot + risk limits (records equity history)
    GET  /api/history           normalized equity curve vs S&P 500
    GET  /api/macro             macro regime snapshot (cached 5 min)
    GET  /api/trades            trade ledger
    GET  /api/journal           theses + lessons
    POST /api/chat              SSE stream of agent events for one message
    POST /api/approval/{id}     resolve a pending order approval
"""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import settings
from .history import EquityHistory
from .memory import Journal
from .portfolio import Portfolio
from .risk import RiskManager

WEB_DIR = Path(__file__).parent / "web"
APPROVAL_TIMEOUT_SECONDS = 300


# ---------- pending-order approvals (browser modal flow) ----------

class ApprovalHub:
    """Bridges the agent thread (which blocks waiting for a decision) and the
    HTTP endpoint where the human clicks approve/deny."""

    def __init__(self):
        self._pending: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.emit = None  # set by the active chat stream

    def approve_fn(self, order: dict) -> bool:
        req_id = uuid.uuid4().hex[:8]
        event = threading.Event()
        with self._lock:
            self._pending[req_id] = {"order": order, "event": event, "decision": None}
        if self.emit:
            self.emit({"type": "approval_request", "id": req_id, "order": order})
        decided = event.wait(timeout=APPROVAL_TIMEOUT_SECONDS)
        with self._lock:
            entry = self._pending.pop(req_id)
        if not decided:
            return False  # timeout = deny, never silently execute
        return bool(entry["decision"])

    def resolve(self, req_id: str, approve: bool) -> bool:
        with self._lock:
            entry = self._pending.get(req_id)
            if entry is None:
                return False
            entry["decision"] = approve
        entry["event"].set()
        return True


# ---------- app state ----------

class AppState:
    def __init__(self):
        from .tools import market_data

        self.market_data = market_data
        self.portfolio = Portfolio(
            settings.data_dir / "portfolio.json",
            starting_cash=settings.paper_starting_cash,
        )
        self.risk = RiskManager(settings.risk)
        self.journal = Journal(settings.data_dir)
        self.history = EquityHistory(settings.data_dir / "equity_history.json")
        self.approvals = ApprovalHub()
        self.chat_lock = threading.Lock()  # one agent turn at a time
        self._macro_cache: tuple[float, dict] | None = None
        self._agent = None

    @property
    def agent(self):
        if self._agent is None:
            from .agent import InvestmentAgent
            from .brokers.paper import PaperBroker

            if settings.execution_mode == "live":
                from .brokers.alpaca import AlpacaBroker

                broker = AlpacaBroker(
                    settings.alpaca_api_key,
                    settings.alpaca_secret_key,
                    settings.alpaca_base_url,
                    self.portfolio,
                    self.market_data.last_price,
                )
            else:
                broker = PaperBroker(self.portfolio, self.market_data.last_price)

            approve_fn = None if settings.auto_approve else self.approvals.approve_fn
            self._agent = InvestmentAgent(
                settings, self.portfolio, broker, self.risk, self.journal, approve_fn
            )
        return self._agent

    def macro(self) -> dict:
        now = time.time()
        if self._macro_cache and now - self._macro_cache[0] < 300:
            return self._macro_cache[1]
        from .tools import macro

        snap = macro.get_macro_snapshot()
        self._macro_cache = (now, snap)
        return snap


state = AppState()
app = FastAPI(title="JARVIS Dashboard")


# ---------- API ----------

@app.get("/api/portfolio")
def api_portfolio():
    snap = state.portfolio.snapshot(state.market_data.last_price)
    snap["mode"] = settings.execution_mode
    snap["auto_approve"] = settings.auto_approve
    snap["risk_limits"] = state.risk.describe()
    try:
        benchmark = state.market_data.last_price("^GSPC")
    except Exception:
        benchmark = None
    state.history.record(snap["equity"], benchmark)
    return snap


@app.get("/api/history")
def api_history():
    return state.history.read()


@app.get("/api/macro")
def api_macro():
    return state.macro()


@app.get("/api/trades")
def api_trades():
    return list(reversed(state.portfolio.trades[-200:]))


@app.get("/api/journal")
def api_journal():
    data = state.journal.read(limit=50)
    data["theses"].reverse()
    data["lessons"].reverse()
    return data


class ChatRequest(BaseModel):
    message: str


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    """Run one agent turn, streaming events as SSE.

    Event types: text, approval_request, error, done.
    """
    q: queue.Queue = queue.Queue()
    state.approvals.emit = q.put

    def worker():
        if not state.chat_lock.acquire(blocking=False):
            q.put({"type": "error", "message": "The agent is already busy with another turn."})
            q.put({"type": "done"})
            return
        try:
            state.agent.run_turn(
                req.message, lambda t: q.put({"type": "text", "text": t})
            )
        except Exception as exc:
            q.put({"type": "error", "message": str(exc)})
        finally:
            state.chat_lock.release()
            q.put({"type": "done"})

    threading.Thread(target=worker, daemon=True).start()

    def event_stream():
        while True:
            try:
                item = q.get(timeout=600)
            except queue.Empty:
                item = {"type": "error", "message": "Agent turn timed out."}
                yield f"data: {json.dumps(item)}\n\n"
                break
            yield f"data: {json.dumps(item)}\n\n"
            if item["type"] == "done":
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ApprovalDecision(BaseModel):
    approve: bool


@app.post("/api/approval/{req_id}")
def api_approval(req_id: str, decision: ApprovalDecision):
    ok = state.approvals.resolve(req_id, decision.approve)
    return {"resolved": ok}


# ---------- static frontend ----------

@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
