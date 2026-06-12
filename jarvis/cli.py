"""Command-line interface for JARVIS.

    python -m jarvis chat                interactive session with the agent
    python -m jarvis analyze NVDA        VC-style deep-dive on one ticker
    python -m jarvis briefing            daily macro + portfolio briefing
    python -m jarvis auto [--interval N] autonomous management loop
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
        broker = PaperBroker(portfolio, market_data.last_price)

    approve_fn = None if auto_approve else _interactive_approval
    return InvestmentAgent(settings, portfolio, broker, risk, journal, approve_fn)


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

    sub.add_parser("portfolio", help="print holdings").set_defaults(
        func=cmd_portfolio
    )

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
