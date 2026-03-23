"""命令行入口 — 启动知衡 Web 服务。"""

from __future__ import annotations

import argparse
from pathlib import Path

from quant_balance.web_demo import DEFAULT_HOST, DEFAULT_PORT, run_demo_web_server

DEFAULT_EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "examples" / "demo_backtest.csv"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quant-balance",
        description="知衡（QuantBalance）— A股个人量化操作系统",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Web 服务绑定地址")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Web 服务绑定端口")
    parser.add_argument("--developer-mode", action="store_true", help="启用开发者模式（允许本地路径输入）")
    parser.add_argument("--open-browser", action="store_true", help="启动后自动打开浏览器")
    parser.add_argument("--example-csv", default=str(DEFAULT_EXAMPLE_PATH), help="示例 CSV 文件路径")
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    example_csv_path = Path(args.example_csv)
    if not example_csv_path.exists():
        import sys
        print(f"错误：找不到示例 CSV 文件 {example_csv_path}。请检查 --example-csv 参数。", file=sys.stderr)
        return 2

    run_demo_web_server(
        host=args.host,
        port=args.port,
        developer_mode=args.developer_mode,
        open_browser=args.open_browser,
        example_csv_path=example_csv_path,
    )
    return 0
