"""Command-line interface for JARVIS.

    python -m jarvis chat                interactive session with the agent
    python -m jarvis analyze NVDA        VC-style deep-dive on one ticker
    python -m jarvis briefing            daily macro + portfolio briefing
    python -m jarvis auto [--interval N] autonomous management loop
    python -m jarvis dashboard           web dashboard at localhost:8000
    python -m jarvis telegram            control the agent from Telegram
    python -m jarvis models [list|pull|use [name]]  manage local AI models
    python -m jarvis backtest "NVDA=0.4,GLD=0.2"    backtest an allocation
    python -m jarvis strategy NVDA --type sma_cross  backtest a timing strategy
    python -m jarvis optimize NVDA --type sma_cross  tune strategy parameters
    python -m jarvis portfolio           print holdings (no LLM call)
"""

from __future__ import annotations

import argparse
import sys
import time

from .config import settings
from .memory import Journal
from .portfolio import Portfolio
from .prompts import ANALYZE_PROMPT, AUTO_CYCLE_PROMPT, BRIEFING_PROMPT
from .risk import RiskManager


def _build_broker(portfolio):
    from .tools import market_data

    if settings.execution_mode == "live":
        from .brokers.alpaca import AlpacaBroker

        return AlpacaBroker(
            settings.alpaca_api_key,
            settings.alpaca_secret_key,
            settings.alpaca_base_url,
            portfolio,
            market_data.last_price,
        )
    if settings.execution_mode == "crypto":
        from .brokers.ccxt_broker import CCXTBroker

        return CCXTBroker(
            settings.ccxt_exchange,
            settings.ccxt_api_key,
            settings.ccxt_secret,
            portfolio,
            sandbox=settings.ccxt_sandbox,
            password=settings.ccxt_password,
            quote=settings.ccxt_quote,
        )
    from .brokers.paper import PaperBroker

    return PaperBroker(
        portfolio,
        market_data.last_price,
        slippage_bps=settings.fill_slippage_bps,
        commission=settings.commission_per_order,
    )


def _build_agent(auto_approve: bool):
    from .agent import InvestmentAgent

    portfolio = Portfolio(
        settings.data_dir / "portfolio.json",
        starting_cash=settings.paper_starting_cash,
    )
    risk = RiskManager(settings.risk)
    journal = Journal(settings.data_dir)
    broker = _build_broker(portfolio)

    approve_fn = None if auto_approve else _interactive_approval
    return InvestmentAgent(
        settings,
        portfolio,
        broker,
        risk,
        journal,
        approve_fn,
        history_path=settings.data_dir / "chat_history.json",
    )


def _interactive_approval(order: dict) -> bool:
    print("\n" + "=" * 60)
    print("  ORDER APPROVAL REQUIRED")
    print("=" * 60)
    print(f"  {order['side'].upper()} {order['qty']} {order['symbol']}")
    print(f"  Est. price : ${order['est_price']:,.2f}")
    print(f"  Est. value : ${order['est_value']:,.2f}")
    print(f"  Conviction : {order['conviction']}")
    print(f"  Rationale  : {order['rationale']}")
    print("=" * 60)
    answer = input("  Approve this order? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def _stream_print(text: str) -> None:
    print(text, end="", flush=True)


def cmd_chat(args) -> None:
    agent = _build_agent(auto_approve=settings.auto_approve)
    mode = settings.execution_mode
    approval = "auto-approve" if settings.auto_approve else "ask before orders"
    print(
        f"JARVIS ready — {agent.provider}:{agent.model}, {mode} mode, "
        f"{approval}. Type 'exit' to quit.\n"
    )
    while True:
        try:
            user = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        if user.lower() in ("exit", "quit"):
            break
        print("\njarvis > ", end="", flush=True)
        agent.run_turn(user, _stream_print)
        print("\n")


def cmd_analyze(args) -> None:
    agent = _build_agent(auto_approve=True)  # analysis never places orders
    agent.run_turn(ANALYZE_PROMPT.format(symbol=args.symbol.upper()), _stream_print)
    print()


def cmd_briefing(args) -> None:
    agent = _build_agent(auto_approve=True)  # briefing never places orders
    agent.run_turn(BRIEFING_PROMPT, _stream_print)
    print()


def cmd_auto(args) -> None:
    if settings.execution_mode in ("live", "crypto") and not settings.auto_approve:
        sys.exit(
            f"Refusing to run the autonomous loop in {settings.execution_mode} "
            "mode without AUTO_APPROVE=true. Set it explicitly if you accept "
            "unattended real-money trading, or switch EXECUTION_MODE=paper."
        )
    print(
        f"Autonomous loop: {settings.execution_mode} mode, "
        f"cycle every {args.interval}s. Ctrl-C to stop.\n"
    )
    cycle = 0
    while True:
        cycle += 1
        print(f"\n===== cycle {cycle} — {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        # Fresh agent per cycle: each cycle re-reads portfolio + journal from
        # disk, so context stays small and state stays on disk where it belongs.
        agent = _build_agent(auto_approve=True)
        try:
            _run_pending_orders(agent.portfolio)
            _run_protective_stops(agent.portfolio)
            _run_alert_check(agent.portfolio)
            agent.run_turn(AUTO_CYCLE_PROMPT, _stream_print)
        except Exception as exc:
            print(f"\n[cycle failed: {exc}]", file=sys.stderr)
        print()
        if args.once:
            break
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.")
            break


def _run_protective_stops(portfolio: Portfolio) -> None:
    """Auto-exit positions whose protective levels triggered; never fatal."""
    try:
        from .stops import StopBook, StopEngine
        from .tools import market_data

        book = StopBook(settings.data_dir / "stops.json")
        if not book.all() and not settings.roi_table:
            return
        broker = _build_broker(portfolio)
        engine = StopEngine(
            book, portfolio, broker, market_data.last_price, roi_table=settings.roi_table
        )
        for exit_ in engine.run():
            if "error" in exit_:
                print(f"[STOP/failed] {exit_['symbol']}: {exit_['error']}")
            else:
                print(
                    f"[STOP] Sold {exit_['qty']} {exit_['symbol']} @ "
                    f"${exit_['exit_price']:,.2f} — {exit_['reason']}"
                )
    except Exception as exc:
        print(f"[stop check failed: {exc}]", file=sys.stderr)


def _run_pending_orders(portfolio: Portfolio) -> None:
    """Fill any triggered limit/stop/OCO orders; never fatal."""
    try:
        from .orders import OrderBook, OrderEngine
        from .tools import market_data

        book = OrderBook(settings.data_dir / "pending_orders.json")
        if not book.all():
            return
        broker = _build_broker(portfolio)
        engine = OrderEngine(
            book, portfolio, broker, RiskManager(settings.risk), market_data.last_price
        )
        for ev in engine.run():
            if ev["status"] == "filled":
                print(
                    f"[ORDER] {ev['side'].upper()} {ev['qty']} {ev['symbol']} @ "
                    f"${ev['fill_price']:,.2f} ({ev['trigger']} order filled)"
                )
            else:
                print(f"[ORDER/{ev['status']}] {ev['symbol']}: {ev.get('reason', '')}")
    except Exception as exc:
        print(f"[pending-order check failed: {exc}]", file=sys.stderr)


def _run_alert_check(portfolio: Portfolio) -> None:
    """Evaluate alert rules and notify configured channels; never fatal."""
    try:
        from .alerts import AlertManager
        from .history import EquityHistory
        from .tools import market_data

        snap = portfolio.snapshot(market_data.last_price)
        history = EquityHistory(settings.data_dir / "equity_history.json")
        try:
            benchmark = market_data.last_price("^GSPC")
        except Exception:
            benchmark = None
        history.record(snap["equity"], benchmark)
        fired = AlertManager(settings).process(snap, history.read())
        for alert in fired:
            print(f"[ALERT/{alert['severity']}] {alert['title']} — {alert['detail']}")
    except Exception as exc:
        print(f"[alert check failed: {exc}]", file=sys.stderr)


def cmd_strategy(args) -> None:
    from .strategy import run_strategy

    result = run_strategy(
        args.symbol,
        strategy=args.type,
        period=args.period,
        stop_loss_pct=args.stop_loss,
    )
    s, b = result["strategy_performance"], result["buy_hold_performance"]
    print(
        f"\n{result['symbol']} · {result['strategy']} · "
        f"{result['start']} → {result['end']}"
    )
    sl = f"{args.stop_loss}%" if args.stop_loss else "none"
    print(f"Params: {result['params']}  ·  stop-loss: {sl}\n")
    print(f"{'':<20}{'Strategy':>12}{'Buy & Hold':>12}")
    for label, key in [
        ("Total return %", "total_return_pct"),
        ("CAGR %", "cagr_pct"),
        ("Sharpe", "sharpe_ratio"),
        ("Max drawdown %", "max_drawdown_pct"),
    ]:
        print(f"{label:<20}{str(s[key]):>12}{str(b[key]):>12}")
    print(
        f"\nTrades: {result['num_trades']}  ·  win rate: {result['win_rate_pct']}%  "
        f"·  avg win: {result['avg_win_pct']}%  ·  avg loss: {result['avg_loss_pct']}%"
    )


def cmd_optimize(args) -> None:
    from .optimize import run_optimize

    result = run_optimize(
        args.symbol,
        strategy=args.type,
        period=args.period,
        objective=args.objective,
        method=args.method,
    )
    print(
        f"\n{result['symbol']} · {result['strategy']} · objective={result['objective']} "
        f"· {result['method']} · {result['combinations_tested']} combos tested\n"
    )
    best = result["best"]
    print(f"Best params: {best['params']}")
    print(
        f"  return {best['total_return_pct']}%  ·  Sharpe {best['sharpe_ratio']}  "
        f"·  maxDD {best['max_drawdown_pct']}%  ·  {best['num_trades']} trades  "
        f"·  win {best['win_rate_pct']}%\n"
    )
    print("Leaderboard:")
    for i, r in enumerate(result["leaderboard"], 1):
        print(
            f"  {i}. {r['params']}  →  score {r['score']}  "
            f"(ret {r['total_return_pct']}%, Sharpe {r['sharpe_ratio']})"
        )


def cmd_models(args) -> None:
    from .llm.ollama import SUGGESTED_MODELS, OllamaClient, OllamaError

    client = OllamaClient(settings.ollama_host)
    action = args.action or "list"

    if action == "list":
        print(f"Active backend: {settings.llm_provider} · {settings.active_model()}\n")
        if not client.is_available():
            print(f"Ollama not reachable at {settings.ollama_host}.")
            print("Install from https://ollama.com, run `ollama serve`, then retry.\n")
        else:
            installed = client.list_models()
            if installed:
                print("Installed local models:")
                for m in installed:
                    size = f"{m['size_gb']} GB" if m["size_gb"] else "?"
                    print(f"  • {m['name']:<22} {size:>9}  {m['modified']}")
            else:
                print("No local models installed yet.")
        print("\nSuggested (tool-calling capable):")
        for m in SUGGESTED_MODELS:
            print(f"  • {m['name']:<18} {m['size']:>9}  {m['note']}")
        print('\nDownload one with:  python -m jarvis models pull qwen2.5:7b')
        return

    if action == "pull":
        if not args.name:
            sys.exit("Usage: python -m jarvis models pull <name>")
        print(f"Pulling {args.name} … (first download can take a while)")
        last = -1
        try:
            for ev in client.pull(args.name):
                pct = ev.get("percent")
                if pct is not None and int(pct) != last:
                    last = int(pct)
                    bar = "█" * (last // 4) + "░" * (25 - last // 4)
                    print(f"\r  [{bar}] {pct:5.1f}%  {ev['status']:<20}", end="", flush=True)
            print("\nDone.")
        except OllamaError as exc:
            sys.exit(f"\nPull failed: {exc}")
        return

    if action == "use":
        if not args.name:
            sys.exit("Usage: python -m jarvis models use <name|anthropic:model>")
        if args.name.startswith("anthropic:"):
            settings.select_llm("anthropic", args.name.split(":", 1)[1])
        else:
            if client.is_available() and not client.has_model(args.name):
                print(f"Note: {args.name} is not installed. Pull it first.")
            settings.select_llm("ollama", args.name)
        print(f"Active backend is now: {settings.llm_provider} · {settings.active_model()}")
        return


def cmd_telegram(args) -> None:
    if not settings.telegram_bot_token:
        sys.exit(
            "Set TELEGRAM_BOT_TOKEN (get one from @BotFather) to run the bot. "
            "Optionally set TELEGRAM_CHAT_ID to lock it to your chat."
        )
    if settings.execution_mode == "live" and not settings.auto_approve:
        # Live trades are approved interactively via Telegram buttons — fine.
        pass
    from .telegram_bot import TelegramBot

    TelegramBot(settings, _build_broker).run()


def cmd_dashboard(args) -> None:
    try:
        import uvicorn
    except ImportError:
        sys.exit("The dashboard needs fastapi and uvicorn: pip install -r requirements.txt")
    print(f"JARVIS dashboard → http://{args.host}:{args.port}")
    uvicorn.run("jarvis.server:app", host=args.host, port=args.port, log_level="warning")


def cmd_backtest(args) -> None:
    from .backtest import run_backtest

    weights = {}
    for part in args.weights.split(","):
        symbol, _, weight = part.strip().partition("=")
        weights[symbol.upper()] = float(weight)
    result = run_backtest(
        weights,
        period=args.period,
        rebalance=args.rebalance,
        benchmark_symbol=args.benchmark,
    )
    print(f"\nBacktest {result['start']} → {result['end']} "
          f"(rebalance: {result['rebalance']}, costs: {result['cost_bps']} bps)\n")
    rows = [("", "Portfolio", result.get("benchmark_symbol", "Benchmark"))]
    bench = result.get("benchmark", {})
    for key, label in [
        ("total_return_pct", "Total return %"),
        ("cagr_pct", "CAGR %"),
        ("annualized_volatility_pct", "Volatility %"),
        ("sharpe_ratio", "Sharpe"),
        ("max_drawdown_pct", "Max drawdown %"),
    ]:
        rows.append((label, result["portfolio"][key], bench.get(key, "—")))
    for label, a, b in rows:
        print(f"{label:<18}{str(a):>12}{str(b):>12}")
    if "excess_cagr_pct" in result:
        print(f"\nExcess CAGR vs benchmark: {result['excess_cagr_pct']:+.2f} pp")


def cmd_portfolio(args) -> None:
    from .tools import market_data

    portfolio = Portfolio(
        settings.data_dir / "portfolio.json",
        starting_cash=settings.paper_starting_cash,
    )
    snap = portfolio.snapshot(market_data.last_price)
    print(f"\nEquity: ${snap['equity']:,.2f}   Cash: ${snap['cash']:,.2f}")
    print(f"Trades today: {snap['trades_today']}   Total: {snap['total_trades']}\n")
    if not snap["positions"]:
        print("No open positions.")
        return
    header = f"{'SYMBOL':<8}{'QTY':>10}{'AVG COST':>12}{'PRICE':>12}{'VALUE':>14}{'P&L':>12}{'P&L %':>9}"
    print(header)
    print("-" * len(header))
    for p in snap["positions"]:
        print(
            f"{p['symbol']:<8}{p['qty']:>10}{p['avg_cost']:>12,.2f}"
            f"{p['price']:>12,.2f}{p['value']:>14,.2f}"
            f"{p['unrealized_pnl']:>12,.2f}{p['unrealized_pnl_pct']:>8.2f}%"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="jarvis", description="JARVIS — AI investment agent"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("chat", help="interactive session").set_defaults(func=cmd_chat)

    p_analyze = sub.add_parser("analyze", help="deep-dive on a ticker")
    p_analyze.add_argument("symbol")
    p_analyze.set_defaults(func=cmd_analyze)

    sub.add_parser("briefing", help="daily briefing").set_defaults(func=cmd_briefing)

    p_auto = sub.add_parser("auto", help="autonomous management loop")
    p_auto.add_argument(
        "--interval",
        type=int,
        default=86_400,
        help="seconds between cycles (default: daily)",
    )
    p_auto.add_argument("--once", action="store_true", help="run a single cycle")
    p_auto.set_defaults(func=cmd_auto)

    p_bt = sub.add_parser("backtest", help="backtest a target-weight allocation")
    p_bt.add_argument("weights", help='e.g. "NVDA=0.4,MSFT=0.3,GLD=0.2"')
    p_bt.add_argument("--period", default="5y", choices=["1y", "2y", "5y", "10y", "max"])
    p_bt.add_argument(
        "--rebalance", default="monthly", choices=["weekly", "monthly", "quarterly"]
    )
    p_bt.add_argument("--benchmark", default="SPY")
    p_bt.set_defaults(func=cmd_backtest)

    p_strat = sub.add_parser("strategy", help="backtest a technical strategy")
    p_strat.add_argument("symbol")
    p_strat.add_argument(
        "--type",
        default="sma_cross",
        choices=["sma_cross", "rsi", "macd_cross", "bollinger"],
    )
    p_strat.add_argument("--period", default="5y")
    p_strat.add_argument(
        "--stop-loss", type=float, default=None, help="stop-loss percent, e.g. 8"
    )
    p_strat.set_defaults(func=cmd_strategy)

    p_opt = sub.add_parser("optimize", help="grid-search strategy parameters")
    p_opt.add_argument("symbol")
    p_opt.add_argument(
        "--type",
        default="sma_cross",
        choices=["sma_cross", "rsi", "macd_cross", "bollinger"],
    )
    p_opt.add_argument("--period", default="5y")
    p_opt.add_argument(
        "--objective", default="sharpe", choices=["sharpe", "return", "cagr"]
    )
    p_opt.add_argument("--method", default="grid", choices=["grid", "random"])
    p_opt.set_defaults(func=cmd_optimize)

    p_models = sub.add_parser("models", help="list / pull / select local AI models")
    p_models.add_argument(
        "action", nargs="?", default="list", choices=["list", "pull", "use"]
    )
    p_models.add_argument("name", nargs="?", help="model name (for pull/use)")
    p_models.set_defaults(func=cmd_models)

    sub.add_parser("telegram", help="run the Telegram bot").set_defaults(
        func=cmd_telegram
    )

    p_dash = sub.add_parser("dashboard", help="launch the web dashboard")
    p_dash.add_argument("--host", default="127.0.0.1", help="bind address")
    p_dash.add_argument("--port", type=int, default=8000)
    p_dash.set_defaults(func=cmd_dashboard)

    sub.add_parser("portfolio", help="print holdings").set_defaults(
        func=cmd_portfolio
    )

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
