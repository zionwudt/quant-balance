from __future__ import annotations

import argparse
import json
from pathlib import Path

from quant_balance.backtest import BacktestEngine
from quant_balance.demo import parse_csv_text_to_bars
from quant_balance.models import AccountConfig
from quant_balance.report import BacktestReport
from quant_balance.strategy import MovingAverageCrossStrategy
from quant_balance.web_demo import DEFAULT_HOST, DEFAULT_PORT, run_demo_web_server

DEFAULT_SYMBOL = "600519.SH"
DEFAULT_EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "examples" / "demo_backtest.csv"
ROOT_COMMAND_HINT = "Use 'quant-balance --help' to explore commands, or try 'quant-balance demo' and 'quant-balance web-demo'."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quant-balance", description="QuantBalance CLI")
    subparsers = parser.add_subparsers(dest="command")

    demo_parser = subparsers.add_parser("demo", help="run the built-in backtest demo")
    demo_parser.add_argument("--csv", default=str(DEFAULT_EXAMPLE_PATH), help="path to demo CSV file")
    demo_parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="symbol to use for the demo bars")
    demo_parser.add_argument("--initial-cash", type=float, default=100_000.0, help="initial cash for the backtest")
    demo_parser.add_argument("--short-window", type=int, default=5, help="short moving average window")
    demo_parser.add_argument("--long-window", type=int, default=10, help="long moving average window")
    demo_parser.add_argument("--json", action="store_true", help="print the full report as JSON")

    web_demo_parser = subparsers.add_parser("web-demo", help="run the local web demo shell")
    web_demo_parser.add_argument("--host", default=DEFAULT_HOST, help="host to bind the local web demo")
    web_demo_parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="port to bind the local web demo")
    web_demo_parser.add_argument("--developer-mode", action="store_true", help="enable local path mode for developers")
    web_demo_parser.add_argument("--example-csv", default=str(DEFAULT_EXAMPLE_PATH), help="path to the example CSV used by the web demo")
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "demo":
        report = run_demo_backtest(
            csv_path=Path(args.csv),
            symbol=args.symbol,
            initial_cash=args.initial_cash,
            short_window=args.short_window,
            long_window=args.long_window,
        )

        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(format_demo_summary(report, csv_path=Path(args.csv), symbol=args.symbol, short_window=args.short_window, long_window=args.long_window))
        return 0

    if args.command == "web-demo":
        run_demo_web_server(
            host=args.host,
            port=args.port,
            developer_mode=args.developer_mode,
            example_csv_path=Path(args.example_csv),
        )
        return 0

    print("QuantBalance is ready.")
    print(ROOT_COMMAND_HINT)
    return 0


def run_demo_backtest(
    *,
    csv_path: Path,
    symbol: str,
    initial_cash: float,
    short_window: int,
    long_window: int,
) -> BacktestReport:
    if initial_cash <= 0:
        raise ValueError("initial cash must be greater than 0")
    if short_window < 2 or long_window < 3 or short_window >= long_window:
        raise ValueError("invalid moving average windows: short_window must be >= 2 and < long_window")

    csv_text = csv_path.read_text(encoding="utf-8")
    bars = parse_csv_text_to_bars(csv_text=csv_text, symbol=symbol)
    strategy = MovingAverageCrossStrategy(short_window=short_window, long_window=long_window)
    config = AccountConfig(initial_cash=initial_cash, max_position_ratio=1.0, max_positions=1, max_drawdown_ratio=1.0)
    engine = BacktestEngine(config=config, strategy=strategy)
    result = engine.run(bars)
    if result.report is None:
        raise RuntimeError("backtest did not produce a report")
    return result.report


def format_demo_summary(report: BacktestReport, *, csv_path: Path, symbol: str, short_window: int, long_window: int) -> str:
    lines = [
        "QuantBalance Demo Backtest",
        f"Data: {csv_path}",
        f"Symbol: {symbol}",
        f"Strategy: MA cross ({short_window}/{long_window})",
        "",
        "Summary",
        f"- Final equity: {report.final_equity:.2f}",
        f"- Total return: {report.total_return_pct:.2f}%",
        f"- Max drawdown: {report.max_drawdown_pct:.2f}%",
        f"- Trades: {report.trades_count}",
        f"- Win rate: {report.win_rate_pct:.2f}%",
    ]
    if report.max_drawdown_start and report.max_drawdown_end:
        lines.append(f"- Drawdown window: {report.max_drawdown_start.isoformat()} -> {report.max_drawdown_end.isoformat()}")
    return "\n".join(lines)
