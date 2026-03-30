"""数据层公共配置与错误定义。

配置说明：
- config/config.toml: 主配置文件（需从 config.example.toml 复制）
- ~/.quant_balance/cache.db: 本地数据缓存（SQLite）

数据源优先级：
- DEFAULT_DAILY_PROVIDERS: akshare > baostock > tushare
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Sequence
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.toml"

CACHE_DB_PATH = Path.home() / ".quant_balance" / "cache.db"
DEFAULT_DAILY_PROVIDERS = ("akshare", "baostock", "tushare")
SUPPORTED_DAILY_PROVIDERS = frozenset(DEFAULT_DAILY_PROVIDERS)
TUSHARE_REGISTER_URL = "https://tushare.pro/register"
TUSHARE_TOKEN_PLACEHOLDER = "你的token"


class DataLoadError(ValueError):
    """数据加载异常。"""


def load_app_config() -> dict:
    """读取应用配置；未配置时返回空字典。"""
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def get_app_config_path() -> Path:
    """返回应用配置文件路径。"""

    return _CONFIG_PATH


def get_tushare_config_status(*, check_connection: bool = False) -> dict[str, object]:
    """返回 Tushare token 当前配置状态。"""

    config_exists = _CONFIG_PATH.exists()
    config = load_app_config() if config_exists else {}
    token = str((config.get("tushare") or {}).get("token", "")).strip()
    token_placeholder = token == TUSHARE_TOKEN_PLACEHOLDER
    token_configured = bool(token) and not token_placeholder

    status: dict[str, object] = {
        "config_exists": config_exists,
        "config_path": str(_CONFIG_PATH),
        "token_configured": token_configured,
        "token_placeholder": token_placeholder,
        "connection_checked": check_connection and token_configured,
        "connection_ok": None,
        "register_url": TUSHARE_REGISTER_URL,
    }

    if not config_exists:
        status["message"] = "未找到 config/config.toml。"
        return status
    if not token_configured:
        status["message"] = "config/config.toml 中的 [tushare] token 未设置。"
        return status
    if not check_connection:
        status["message"] = "Tushare token 已配置，尚未验证连接。"
        return status

    connection_ok, message = validate_tushare_token(token)
    status["connection_ok"] = connection_ok
    status["message"] = message
    return status


def load_tushare_token() -> str:
    """从 config/config.toml 读取 Tushare token。"""
    if not _CONFIG_PATH.exists():
        raise DataLoadError(
            f"未找到配置文件 {_CONFIG_PATH}，"
            "请复制 config/config.example.toml 为 config/config.toml 并填入你的 Tushare token。"
        )
    config = load_app_config()
    token = (config.get("tushare") or {}).get("token", "")
    if not token or token == TUSHARE_TOKEN_PLACEHOLDER:
        raise DataLoadError(
            "config/config.toml 中的 [tushare] token 未设置，"
            f"请填入你的 Tushare token。获取方式：{TUSHARE_REGISTER_URL}"
        )
    return token


def validate_tushare_token(token: str) -> tuple[bool, str]:
    """验证 Tushare token 是否可用。"""

    normalized = token.strip()
    if not normalized or normalized == TUSHARE_TOKEN_PLACEHOLDER:
        return False, "Tushare token 不能为空。"

    try:
        import tushare as ts
    except ImportError:
        return False, "当前环境未安装 tushare，无法验证 token。"

    try:
        pro = ts.pro_api(normalized)
        result = pro.trade_cal(exchange="", start_date="20240102", end_date="20240105")
    except Exception as exc:  # noqa: BLE001
        return False, f"Tushare token 验证失败：{exc}"

    if result is None:
        return False, "Tushare 未返回结果，请检查 token 是否有效。"
    return True, "Tushare token 验证成功。"


def save_tushare_token(token: str) -> Path:
    """保存 Tushare token 到 config/config.toml。"""

    normalized = token.strip()
    if not normalized or normalized == TUSHARE_TOKEN_PLACEHOLDER:
        raise ValueError("Tushare token 不能为空。")

    config = load_app_config()
    tushare_cfg = dict(config.get("tushare") or {})
    tushare_cfg["token"] = normalized
    config["tushare"] = tushare_cfg

    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(_dump_toml(config), encoding="utf-8")
    return _CONFIG_PATH


def _dump_toml(config: dict) -> str:
    lines: list[str] = []

    for key, value in config.items():
        if isinstance(value, dict):
            if lines:
                lines.append("")
            lines.append(f"[{key}]")
            for inner_key, inner_value in value.items():
                lines.append(f"{inner_key} = {_toml_literal(inner_value)}")
            continue

        lines.append(f"{key} = {_toml_literal(value)}")

    return "\n".join(lines).rstrip() + "\n"


def _toml_literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_literal(item) for item in value) + "]"
    raise TypeError(f"暂不支持写入 TOML 值类型: {type(value)!r}")


def resolve_daily_provider_order(
    *,
    provider: str | None = None,
    providers: Sequence[str] | None = None,
) -> list[str]:
    """解析日线数据源优先级。"""
    if provider is not None and providers is not None:
        raise ValueError("provider 和 providers 不能同时传入")

    if provider is not None:
        raw_order: Sequence[object] = [provider]
    elif providers is not None:
        raw_order = providers
    else:
        config = load_app_config()
        data_cfg = config.get("data") or {}
        if "daily_provider" in data_cfg:
            raw_order = [data_cfg["daily_provider"]]
        else:
            raw_order = data_cfg.get("daily_providers", DEFAULT_DAILY_PROVIDERS)

    if isinstance(raw_order, str):
        raw_order = [raw_order]

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_order:
        name = str(item).strip().lower()
        if not name:
            continue
        if name not in SUPPORTED_DAILY_PROVIDERS:
            supported = ", ".join(DEFAULT_DAILY_PROVIDERS)
            raise DataLoadError(f"不支持的数据源 {item!r}，当前支持: {supported}")
        if name not in seen:
            normalized.append(name)
            seen.add(name)

    if not normalized:
        raise DataLoadError("至少需要配置一个可用的日线数据源。")
    return normalized
