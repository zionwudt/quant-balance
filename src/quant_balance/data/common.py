"""数据层公共配置与错误定义。"""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.toml"

CACHE_DB_PATH = Path.home() / ".quant_balance" / "cache.db"
DEFAULT_DAILY_PROVIDERS = ("akshare", "baostock", "tushare")
SUPPORTED_DAILY_PROVIDERS = frozenset(DEFAULT_DAILY_PROVIDERS)


class DataLoadError(ValueError):
    """数据加载异常。"""


def load_app_config() -> dict:
    """读取应用配置；未配置时返回空字典。"""
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def load_tushare_token() -> str:
    """从 config/config.toml 读取 Tushare token。"""
    if not _CONFIG_PATH.exists():
        raise DataLoadError(
            f"未找到配置文件 {_CONFIG_PATH}，"
            "请复制 config/config.example.toml 为 config/config.toml 并填入你的 Tushare token。"
        )
    config = load_app_config()
    token = (config.get("tushare") or {}).get("token", "")
    if not token or token == "你的token":
        raise DataLoadError(
            "config/config.toml 中的 [tushare] token 未设置，"
            "请填入你的 Tushare token。获取方式：https://tushare.pro/register"
        )
    return token


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
