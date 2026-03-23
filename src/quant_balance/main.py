"""统一主入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

# 默认使用仓库内自带的示例 CSV，保证安装后就能跑通完整演示链路。
DEFAULT_EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "examples" / "demo_backtest.csv"


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        prog="quant-balance",
        description="知衡（QuantBalance）— A股个人量化操作系统",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Web 服务绑定地址")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Web 服务绑定端口")
    parser.add_argument("--developer-mode", action="store_true", help="启用开发者模式（允许本地路径输入）")
    parser.add_argument("--open-browser", action="store_true", help="启动后自动打开接口文档")
    parser.add_argument("--example-csv", default=str(DEFAULT_EXAMPLE_PATH), help="示例 CSV 文件路径")
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    """解析命令行参数，校验示例数据，然后启动 API 服务。"""

    parser = build_parser()
    args = parser.parse_args(argv)

    example_csv_path = Path(args.example_csv)
    if not example_csv_path.exists():
        # 启动前尽早失败，避免服务已经起来后才在页面上暴露更晚的错误。
        print(f"错误：找不到示例 CSV 文件 {example_csv_path}。请检查 --example-csv 参数。", file=sys.stderr)
        return 2

    try:
        from quant_balance.api.app import run_api_server
        run_api_server(
            host=args.host,
            port=args.port,
            developer_mode=args.developer_mode,
            open_browser=args.open_browser,
            example_csv_path=example_csv_path,
        )
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return 0


def main() -> None:
    """执行 CLI，并把返回码转换成当前进程的退出码。"""

    # 统一把返回值映射成进程退出码，便于脚本入口和 `python -m` 保持一致。
    raise SystemExit(run_cli(sys.argv[1:]))


if __name__ == "__main__":
    main()
