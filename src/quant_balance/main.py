"""统一主入口。"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.toml"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def _load_server_config() -> dict:
    """从 config/config.toml 读取 [server] 配置。"""
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, "rb") as f:
        return tomllib.load(f).get("server", {})


def run_cli() -> int:
    """读取配置，启动 API 服务。"""

    server_cfg = _load_server_config()
    host = server_cfg.get("host", DEFAULT_HOST)
    port = server_cfg.get("port", DEFAULT_PORT)

    try:
        from quant_balance.api.app import run_api_server
        run_api_server(host=host, port=port)
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return 0


def main() -> None:
    """执行 CLI，并把返回码转换成当前进程的退出码。"""

    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
