"""向后兼容入口 — 请改用 ``quant_balance.infra.logging``。"""

from quant_balance.infra.logging import (  # noqa: F401
    DEFAULT_LOG_LEVEL,
    PACKAGE_LOGGER_NAME,
    StructuredLogFormatter,
    configure_logging,
    get_logger,
    log_event,
)

__all__ = [
    "DEFAULT_LOG_LEVEL",
    "PACKAGE_LOGGER_NAME",
    "StructuredLogFormatter",
    "configure_logging",
    "get_logger",
    "log_event",
]
