"""向后兼容入口 — 请改用 ``quant_balance.infra.scheduler``。"""

from quant_balance.infra.scheduler import (  # noqa: F401
    DailyScanScheduler,
    SchedulerConfig,
    build_scan_id,
    build_scan_signals,
    current_shanghai_date,
    format_notification_body,
    get_previous_trade_day,
    get_scheduler_connection,
    is_trade_day,
    load_last_scan_record,
    load_scheduler_config,
    normalize_trade_date,
    parse_scan_time,
    persist_scan_record,
    persist_scan_signals,
    query_trade_calendar,
    resolve_scan_trade_date,
    run_daily_scan,
    send_scan_notifications,
    shanghai_now,
    _resolve_signal_price,
    _load_apscheduler,
)

# 以下名称原先通过 scheduler.py 顶部的 import 语句暴露在模块命名空间中，
# 测试可能从 quant_balance.scheduler 直接导入或 patch 这些名称。
from quant_balance.core.signals import (  # noqa: F401
    Signal,
    default_signal_reason,
    list_recent_signals,
    persist_signals,
    resolve_signal_name,
    serialize_signal,
    suggest_signal_quantity,
)
from quant_balance.core.strategies import SIGNAL_REGISTRY  # noqa: F401
from quant_balance.data import load_dataframe  # noqa: F401
from quant_balance.data.common import (  # noqa: F401
    CACHE_DB_PATH,
    DataLoadError,
    load_app_config,
    load_tushare_token,
)
from quant_balance.services.screening_service import run_stock_screening  # noqa: F401

__all__ = [
    "DailyScanScheduler",
    "SchedulerConfig",
    "build_scan_id",
    "build_scan_signals",
    "current_shanghai_date",
    "format_notification_body",
    "get_previous_trade_day",
    "get_scheduler_connection",
    "is_trade_day",
    "load_last_scan_record",
    "load_scheduler_config",
    "normalize_trade_date",
    "parse_scan_time",
    "persist_scan_record",
    "persist_scan_signals",
    "query_trade_calendar",
    "resolve_scan_trade_date",
    "run_daily_scan",
    "send_scan_notifications",
    "shanghai_now",
]
