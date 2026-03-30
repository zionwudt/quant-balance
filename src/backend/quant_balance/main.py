"""统一主入口。"""

from __future__ import annotations

import sys
import tomllib

from quant_balance.data.common import TUSHARE_REGISTER_URL, get_tushare_config_status
from quant_balance.paths import CONFIG_PATH

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def _load_server_config() -> dict:
    """从 config/config.toml 读取 [server] 配置。"""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f).get("server", {})


def _format_tushare_setup_guide(status: dict[str, object]) -> str:
    reason = "未找到 config/config.toml。" if not status["config_exists"] else "config/config.toml 中的 [tushare] token 未设置。"
    return "\n".join([
        "首次使用？请先配置 Tushare Token：",
        f"原因：{reason}",
        f"配置文件：{status['config_path']}",
        "1. 复制 config/config.example.toml -> config/config.toml",
        "2. 在 [tushare] 下填入你的 token",
        f"3. Token 获取地址：{TUSHARE_REGISTER_URL}",
    ])


def check_config_or_guide() -> int:
    """检查首次使用配置；缺失时打印引导信息。"""

    status = get_tushare_config_status(check_connection=False)
    if status["token_configured"]:
        return 0

    print(_format_tushare_setup_guide(status), file=sys.stderr)
    return 1


def run_cli() -> int:
    """读取配置，启动 API 服务。"""

    guide_code = check_config_or_guide()
    if guide_code != 0:
        return guide_code

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
