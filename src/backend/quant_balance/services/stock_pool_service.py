"""股票池服务 —— 历史池过滤与 API 输出编排。"""

from __future__ import annotations

from dataclasses import asdict
from time import perf_counter

from quant_balance.data.stock_pool import filter_pool_at_date
from quant_balance.logging_utils import get_logger, log_event

logger = get_logger(__name__)


def run_stock_pool_filter(
    *,
    pool_date: str,
    filters: dict | None = None,
    symbols: list[str] | None = None,
    data_provider: str | None = None,
) -> dict[str, object]:
    """执行历史股票池过滤并返回 API 友好结构。"""

    started_at = perf_counter()
    records = filter_pool_at_date(
        pool_date,
        filters=filters,
        symbols=symbols,
    )
    payload = {
        "symbols": [record.ts_code for record in records],
        "items": [asdict(record) for record in records],
        "total_count": len(records),
        "run_context": {
            "pool_date": pool_date,
            "filters": filters or {},
            "symbols_count": len(symbols) if symbols is not None else None,
            "data_provider": data_provider,
        },
    }
    log_event(
        logger,
        "STOCK_POOL_FILTER",
        pool_date=pool_date,
        filters=filters or {},
        requested_symbols_count=len(symbols) if symbols is not None else None,
        total_count=len(records),
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
    )
    return payload
