"""API 公共依赖 — 错误日志、异常处理等。"""

from __future__ import annotations

import logging
from typing import Any

from quant_balance.infra.logging import get_logger, log_event

logger = get_logger(__name__)


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

