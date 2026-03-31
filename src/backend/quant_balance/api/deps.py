"""API 公共依赖 — 错误日志、异常处理、认证等。"""

from __future__ import annotations

import logging
from typing import Any

from quant_balance.data.common import load_app_config
from quant_balance.infra.logging import get_logger, log_event

logger = get_logger(__name__)

# ── API Key 认证 ──

_PUBLIC_PATHS = frozenset({"/", "/docs", "/openapi.json", "/redoc", "/favicon.svg"})


def load_api_key() -> str | None:
    """从 config.toml [server] api_key 读取。未配置时返回 None（不启用认证）。"""
    config = load_app_config()
    return str((config.get("server") or {}).get("api_key", "")).strip() or None


def verify_api_key(request_path: str, auth_header: str | None, api_key: str | None) -> bool:
    """校验请求是否通过认证。

    - api_key 为 None 时不启用认证，全部放行
    - 静态资源和公共路径始终放行
    - 其他路径要求 Authorization: Bearer <key> 或 X-API-Key header
    """
    if api_key is None:
        return True
    if request_path in _PUBLIC_PATHS or request_path.startswith("/static"):
        return True
    if auth_header:
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip() == api_key
        return auth_header.strip() == api_key
    return False


def log_api_error(
    *,
    endpoint: str,
    status_code: int,
    exc: Exception,
    context: dict[str, object],
) -> None:
    """统一 API 错误日志。"""
    log_event(
        logger,
        "API_ERROR",
        level=logging.WARNING if status_code < 500 else logging.ERROR,
        exc_info=status_code >= 500,
        endpoint=endpoint,
        status_code=status_code,
        error_type=type(exc).__name__,
        detail=str(exc),
        **context,
    )

