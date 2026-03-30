"""QuantBalance 结构化日志工具。

功能：
- 结构化日志输出（JSON 格式字段）
- 标准化事件命名（如 BACKTEST_RUN、SCREENING_RUN）
- 与 Python logging 模块集成

使用方式：
    from quant_balance.infra.logging import get_logger, log_event
    logger = get_logger(__name__)
    log_event(logger, "MY_EVENT", symbol="AAPL", score=0.95)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

PACKAGE_LOGGER_NAME = "quant_balance"
DEFAULT_LOG_LEVEL = os.getenv("QUANT_BALANCE_LOG_LEVEL", "INFO").upper()


def _normalize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset, range)):
        return [_normalize_value(item) for item in value]

    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _normalize_value(item())
        except (TypeError, ValueError):
            pass

    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            return _normalize_value(tolist())
        except (TypeError, ValueError):
            pass

    return str(value)


class StructuredLogFormatter(logging.Formatter):
    """把事件与字段格式化为统一前缀 + JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "qb_event", None)
        payload = getattr(record, "qb_payload", None)
        message = record.getMessage()

        if event:
            output = f"[quant_balance][{event}]"
        else:
            output = f"[quant_balance] {message}"

        if payload:
            output = (
                f"{output} {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
            )

        if record.exc_info:
            output = f"{output}\n{self.formatException(record.exc_info)}"
        return output


def _resolve_level(level: int | str | None = None) -> int:
    if isinstance(level, int):
        return level
    raw = (level or DEFAULT_LOG_LEVEL).upper()
    return getattr(logging, raw, logging.INFO)


def configure_logging(level: int | str | None = None) -> logging.Logger:
    """配置 quant_balance 包级 logger。"""

    logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    logger.setLevel(_resolve_level(level))

    if logger.handlers:
        return logger

    root_logger = logging.getLogger()
    if root_logger.handlers:
        logger.propagate = True
        return logger

    handler = logging.StreamHandler()
    handler.setFormatter(StructuredLogFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_logger(name: str) -> logging.Logger:
    """获取模块 logger，并确保包级配置已就绪。"""

    configure_logging()
    return logging.getLogger(name)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    """输出标准化事件日志。"""

    payload = {
        key: _normalize_value(value)
        for key, value in fields.items()
        if value is not None
    }
    logger.log(
        level,
        event,
        exc_info=exc_info,
        extra={
            "qb_event": event,
            "qb_payload": payload,
        },
    )

