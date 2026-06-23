"""Web dashboard server for JARVIS.

    python -m jarvis dashboard          # http://127.0.0.1:8000

Endpoints (all under /api require "Authorization: Bearer <token>" when
JARVIS_DASHBOARD_TOKEN is set):
    GET  /                      dashboard SPA
    GET  /api/portfolio         snapshot + sectors + risk limits
    GET  /api/history           normalized equity curve vs S&P 500
    GET  /api/macro             macro regime snapshot (cached 5 min)
    GET  /api/trades            trade ledger
    GET  /api/journal           theses + lessons
    GET  /api/alerts            evaluate + return today's alerts
    POST /api/backtest          run a target-weight backtest
    GET  /api/chat/history      displayable conversation transcript
    POST /api/chat/reset        clear the conversation
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

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .alerts import AlertManager
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
        self.alerts = AlertManager(settings)
        self.approvals = ApprovalHub()
        self.chat_lock = threading.Lock()  # one agent turn at a time
        self._macro_cache: tuple[float, dict] | None = None
        self._agent = None
        self._broker = None

    @property
    def broker(self):
        if self._broker is None:
            if settings.execution_mode == "live":
                from .brokers.alpaca import AlpacaBroker

                self._broker = AlpacaBroker(
                    settings.alpaca_api_key,
                    settings.alpaca_secret_key,
                    settings.alpaca_base_url,
                    self.portfolio,
                    self.market_data.last_price,
                )
            elif settings.execution_mode == "crypto":
                from .brokers.ccxt_broker import CCXTBroker

                self._broker = CCXTBroker(
                    settings.ccxt_exchange,
                    settings.ccxt_api_key,
                    settings.ccxt_secret,
                    self.portfolio,
                    sandbox=settings.ccxt_sandbox,
                    password=settings.ccxt_password,
                    quote=settings.ccxt_quote,
                )
            else:
                from .brokers.paper import PaperBroker

                self._broker = PaperBroker(
                    self.portfolio,
                    self.market_data.last_price,
                    slippage_bps=settings.fill_slippage_bps,
                    commission=settings.commission_per_order,
                )
        return self._broker

    @property
    def agent(self):
        if self._agent is None:
            from .agent import InvestmentAgent

            approve_fn = None if settings.auto_approve else self.approvals.approve_fn
            self._agent = InvestmentAgent(
                settings,
                self.portfolio,
                self.broker,
                self.risk,
                self.journal,
                approve_fn,
                history_path=settings.data_dir / "chat_history.json",
            )
        return self._agent

    def run_protective_stops(self) -> list[dict]:
        from .stops import StopBook, StopEngine

        book = StopBook(settings.data_dir / "stops.json")
        if not book.all() and not settings.roi_table:
            return []
        engine = StopEngine(
            book,
            self.portfolio,
            self.broker,
            self.market_data.last_price,
            roi_table=settings.roi_table,
        )
        return engine.run()

    def run_pending_orders(self) -> list[dict]:
        from .orders import OrderBook, OrderEngine

        book = OrderBook(settings.data_dir / "pending_orders.json")
        if not book.all():
            return []
        engine = OrderEngine(
            book, self.portfolio, self.broker, self.risk, self.market_data.last_price
        )
        return engine.run()

    def stop_orders(self) -> dict:
        from .stops import StopBook

        return StopBook(settings.data_dir / "stops.json").all()

    def pending_orders(self) -> list[dict]:
        from .orders import OrderBook

        return OrderBook(settings.data_dir / "pending_orders.json").all()

    def rebuild_agent(self) -> None:
        """Drop the cached agent so the next turn picks up a backend change."""
        self._agent = None

    def macro(self) -> dict:
        now = time.time()
        if self._macro_cache and now - self._macro_cache[0] < 300:
            return self._macro_cache[1]
        from .tools import macro

        snap = macro.get_macro_snapshot()
        self._macro_cache = (now, snap)
        return snap

    def snapshot(self) -> dict:
        snap = self.portfolio.snapshot(self.market_data.last_price)
        snap["mode"] = settings.execution_mode
        snap["auto_approve"] = settings.auto_approve
        snap["risk_limits"] = self.risk.describe()
        for pos in snap["positions"]:
            pos["sector"] = self.market_data.get_sector(pos["symbol"])
        snap["sector_allocation"] = {}
        for pos in snap["positions"]:
            snap["sector_allocation"][pos["sector"]] = round(
                snap["sector_allocation"].get(pos["sector"], 0.0) + pos["value"], 2
            )
        snap["protective_orders"] = self.stop_orders()
        snap["pending_orders"] = self.pending_orders()
        snap["country_allocation"] = self.market_data.country_allocation(snap["positions"])
        snap["asset_class_allocation"] = self.market_data.asset_class_allocation(
            snap["positions"]
        )
        return snap


state = AppState()
app = FastAPI(title="JARVIS Dashboard")


# ---------- auth ----------

def _require_auth(request: Request) -> None:
    token = settings.dashboard_token
    if not token:
        return
    supplied = request.headers.get("authorization", "")
    if supplied != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="Invalid or missing token")


api = APIRouter(prefix="/api")


# ---------- API ----------

@api.get("/portfolio")
def api_portfolio(request: Request):
    _require_auth(request)
    snap = state.snapshot()
    try:
        benchmark = state.market_data.last_price("^GSPC")
    except Exception:
        benchmark = None
    state.history.record(snap["equity"], benchmark)
    return snap


@api.get("/history")
def api_history(request: Request):
    _require_auth(request)
    return state.history.read()


@api.get("/macro")
def api_macro(request: Request):
    _require_auth(request)
    return state.macro()


@api.get("/trades")
def api_trades(request: Request):
    _require_auth(request)
    return list(reversed(state.portfolio.trades[-200:]))


@api.get("/journal")
def api_journal(request: Request):
    _require_auth(request)
    data = state.journal.read(limit=50)
    data["theses"].reverse()
    data["lessons"].reverse()
    return data


@api.get("/alerts")
def api_alerts(request: Request):
    _require_auth(request)
    # Pending limit/OCO orders and protective stops both run on this poll so
    # triggers fire even when nobody is chatting; surface them as alerts.
    stop_alerts = []
    try:
        for ev in state.run_pending_orders():
            if ev["status"] != "filled":
                continue
            stop_alerts.append(
                {
                    "severity": "info",
                    "title": f"{ev['side'].upper()} {ev['symbol']} — {ev['trigger']} order filled",
                    "detail": f"{ev['qty']} {ev['symbol']} @ ${ev['fill_price']:,.2f}.",
                }
            )
    except Exception:
        pass
    try:
        for ex in state.run_protective_stops():
            if "error" in ex:
                continue
            stop_alerts.append(
                {
                    "severity": "critical",
                    "title": f"Auto-sold {ex['symbol']} — {ex['reason']}",
                    "detail": f"Exited {ex['qty']} {ex['symbol']} @ ${ex['exit_price']:,.2f}.",
                }
            )
    except Exception:
        pass
    try:
        snap = state.snapshot()
    except Exception:
        return stop_alerts
    return stop_alerts + state.alerts.process(snap, state.history.read())


@api.get("/protective-orders")
def api_protective_orders(request: Request):
    _require_auth(request)
    return state.stop_orders()


@api.get("/pending-orders")
def api_pending_orders(request: Request):
    _require_auth(request)
    return state.pending_orders()


class OptimizeRequest(BaseModel):
    symbol: str
    strategy: str = "sma_cross"
    period: str = "5y"
    objective: str = "sharpe"
    method: str = "grid"


@api.post("/optimize")
def api_optimize(req: OptimizeRequest, request: Request):
    _require_auth(request)
    from .optimize import run_optimize

    try:
        return run_optimize(
            req.symbol,
            strategy=req.strategy,
            period=req.period,
            objective=req.objective,
            method=req.method,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@api.get("/indicators")
def api_indicators(request: Request, symbol: str, period: str = "1y"):
    _require_auth(request)
    from .tools import indicators

    return indicators.get_indicators(symbol, period)


class StrategyRequest(BaseModel):
    symbol: str
    strategy: str = "sma_cross"
    period: str = "5y"
    stop_loss_pct: float | None = None


@api.post("/strategy")
def api_strategy(req: StrategyRequest, request: Request):
    _require_auth(request)
    from .strategy import run_strategy

    try:
        return run_strategy(
            req.symbol,
            strategy=req.strategy,
            period=req.period,
            stop_loss_pct=req.stop_loss_pct,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class BacktestRequest(BaseModel):
    weights: dict[str, float]
    period: str = "5y"
    rebalance: str = "monthly"
    benchmark: str = "SPY"


@api.post("/backtest")
def api_backtest(req: BacktestRequest, request: Request):
    _require_auth(request)
    from .backtest import run_backtest

    try:
        return run_backtest(
            req.weights,
            period=req.period,
            rebalance=req.rebalance,
            benchmark_symbol=req.benchmark,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@api.get("/chat/history")
def api_chat_history(request: Request):
    _require_auth(request)
    return state.agent.transcript()


@api.post("/chat/reset")
def api_chat_reset(request: Request):
    _require_auth(request)
    state.agent.reset()
    return {"reset": True}


class ChatRequest(BaseModel):
    message: str


@api.post("/chat")
def api_chat(req: ChatRequest, request: Request):
    """Run one agent turn, streaming events as SSE.

    Event types: text, approval_request, error, done.
    """
    _require_auth(request)
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


@api.get("/models")
def api_models(request: Request):
    _require_auth(request)
    from .llm.ollama import SUGGESTED_MODELS, OllamaClient

    client = OllamaClient(settings.ollama_host)
    available = client.is_available()
    return {
        "provider": settings.llm_provider,
        "active_model": settings.active_model(),
        "anthropic_model": settings.model,
        "ollama_available": available,
        "ollama_host": settings.ollama_host,
        "installed": client.list_models() if available else [],
        "suggested": SUGGESTED_MODELS,
    }


class SelectModelRequest(BaseModel):
    provider: str
    model: str


@api.post("/models/select")
def api_models_select(req: SelectModelRequest, request: Request):
    _require_auth(request)
    try:
        settings.select_llm(req.provider, req.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    state.rebuild_agent()  # next chat turn uses the new backend
    return {"provider": settings.llm_provider, "active_model": settings.active_model()}


class PullModelRequest(BaseModel):
    name: str


@api.post("/models/pull")
def api_models_pull(req: PullModelRequest, request: Request):
    _require_auth(request)
    from .llm.ollama import OllamaClient, OllamaError

    client = OllamaClient(settings.ollama_host)

    def stream():
        try:
            for event in client.pull(req.name):
                yield f"data: {json.dumps(event)}\n\n"
            yield f'data: {json.dumps({"status": "success", "percent": 100})}\n\n'
        except OllamaError as exc:
            yield f'data: {json.dumps({"error": str(exc)})}\n\n'
        yield f'data: {json.dumps({"done": True})}\n\n'

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ApprovalDecision(BaseModel):
    approve: bool


@api.post("/approval/{req_id}")
def api_approval(req_id: str, decision: ApprovalDecision, request: Request):
    _require_auth(request)
    ok = state.approvals.resolve(req_id, decision.approve)
    return {"resolved": ok}


app.include_router(api)


# ---------- static frontend ----------

@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
