"""Command-line interface for JARVIS.

    python -m jarvis chat                interactive session with the agent
    python -m jarvis analyze NVDA        VC-style deep-dive on one ticker
    python -m jarvis briefing            daily macro + portfolio briefing
    python -m jarvis auto [--interval N] autonomous management loop
    python -m jarvis dashboard           web dashboard at localhost:8000
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


def _build_agent(auto_approve: bool):
    from .agent import InvestmentAgent
    from .brokers.paper import PaperBroker
    from .tools import market_data

    portfolio = Portfolio(
        settings.data_dir / "portfolio.json",
        starting_cash=settings.paper_starting_cash,
    )
    risk = RiskManager(settings.risk)
    journal = Journal(settings.data_dir)

    if settings.execution_mode == "live":
        from .brokers.alpaca import AlpacaBroker

        broker = AlpacaBroker(
            settings.alpaca_api_key,
            settings.alpaca_secret_key,
            settings.alpaca_base_url,
            portfolio,
            market_data.last_price,
        )
    else:
        broker = PaperBroker(
            portfolio,
            market_data.last_price,
            slippage_bps=settings.fill_slippage_bps,
            commission=settings.commission_per_order,
        )

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
    print(f"JARVIS ready — {mode} mode, {approval}. Type 'exit' to quit.\n")
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
    if settings.execution_mode == "live" and not settings.auto_approve:
        sys.exit(
            "Refusing to run the autonomous loop in live mode without "
            "AUTO_APPROVE=true. Set it explicitly if you accept unattended "
            "live trading, or switch EXECUTION_MODE=paper."
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
