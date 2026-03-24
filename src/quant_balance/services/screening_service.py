"""批量筛选服务 — 编排 stock_pool + vectorbt 筛选。"""

from __future__ import annotations

from time import perf_counter

from quant_balance.core.data_adapter import load_multi_dataframes
from quant_balance.core.screening import run_screening
from quant_balance.core.strategies import SIGNAL_REGISTRY
from quant_balance.data.stock_pool import filter_pool_at_date, get_pool_at_date
from quant_balance.logging_utils import get_logger, log_event

logger = get_logger(__name__)


def _has_active_pool_filters(pool_filters: dict | None) -> bool:
    if not pool_filters:
        return False
    return any(
        value not in (None, False, [], {}, "")
        for value in pool_filters.values()
    )


def run_stock_screening(
    *,
    pool_date: str,
    start_date: str,
    end_date: str,
    asset_type: str = "stock",
    signal: str = "sma_cross",
    signal_params: dict | None = None,
    top_n: int = 20,
    cash: float = 100_000.0,
    symbols: list[str] | None = None,
    pool_filters: dict | None = None,
    data_provider: str | None = None,
) -> dict:
    """执行批量选股筛选，返回 API 可直接消费的结果字典。

    参数:
    - pool_date: 股票池基准日期（YYYY-MM-DD），用于获取当时上市的股票
    - symbols: 自定义股票列表，传入则忽略 pool_date
    - signal: 信号函数名
    - top_n: 返回排名前 N 的股票
    """
    signal_func = SIGNAL_REGISTRY.get(signal)
    if signal_func is None:
        raise ValueError(f"未知信号: {signal}，可用: {list(SIGNAL_REGISTRY)}")

    started_at = perf_counter()
    if asset_type == "convertible_bond":
        if _has_active_pool_filters(pool_filters):
            raise ValueError("可转债筛选暂不支持 pool_filters，请直接传入 symbols。")
        if symbols is None:
            raise ValueError("可转债筛选当前需要显式传入 symbols。")
    elif _has_active_pool_filters(pool_filters):
        records = filter_pool_at_date(
            pool_date,
            filters=pool_filters,
            symbols=symbols,
        )
        symbols = [record.ts_code for record in records]
    elif symbols is None:
        symbols = get_pool_at_date(pool_date)
    requested_symbols_count = len(symbols)

    load_kwargs = {"asset_type": asset_type}
    if data_provider is not None:
        load_kwargs["data_provider"] = data_provider
    data = load_multi_dataframes(symbols, start_date, end_date, **load_kwargs)
    if not data:
        payload = {
            "rankings": [],
            "total_screened": 0,
            "run_context": {
                "pool_date": pool_date,
                "start_date": start_date,
                "end_date": end_date,
                "asset_type": asset_type,
                "signal": signal,
                "signal_params": signal_params or {},
                "pool_filters": pool_filters or {},
                "top_n": top_n,
                "data_provider": data_provider,
            },
        }
        log_event(
            logger,
            "SCREENING_RUN",
            stage="service",
            pool_date=pool_date,
            start_date=start_date,
            end_date=end_date,
            asset_type=asset_type,
            signal=signal,
            signal_params=signal_params or {},
            pool_filters=pool_filters or {},
            top_n=top_n,
            requested_symbols_count=requested_symbols_count,
            loaded_symbols_count=0,
            total_screened=0,
            data_provider=data_provider,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        return payload

    result = run_screening(
        data, signal_func,
        cash=cash,
        signal_params=signal_params,
        log_context={
            "pool_date": pool_date,
            "start_date": start_date,
            "end_date": end_date,
            "asset_type": asset_type,
            "signal": signal,
            "data_provider": data_provider,
        },
    )

    rankings_list = []
    if not result.rankings.empty:
        top = result.rankings.head(top_n)
        for symbol, row in top.iterrows():
            rankings_list.append({
                "symbol": symbol,
                **{k: _safe_value(v) for k, v in row.to_dict().items()},
            })

    payload = {
        "rankings": rankings_list,
        "total_screened": len(data),
        "run_context": {
            "pool_date": pool_date,
            "start_date": start_date,
            "end_date": end_date,
            "asset_type": asset_type,
            "signal": signal,
            "signal_params": signal_params or {},
            "pool_filters": pool_filters or {},
            "top_n": top_n,
            "data_provider": data_provider,
        },
    }
    log_event(
        logger,
        "SCREENING_RUN",
        stage="service",
        pool_date=pool_date,
        start_date=start_date,
        end_date=end_date,
        asset_type=asset_type,
        signal=signal,
        signal_params=signal_params or {},
        pool_filters=pool_filters or {},
        top_n=top_n,
        requested_symbols_count=requested_symbols_count,
        loaded_symbols_count=len(data),
        total_screened=len(data),
        ranked_count=len(rankings_list),
        data_provider=data_provider,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
    )
    return payload


def _safe_value(v: object) -> object:
    """处理 NaN 和 numpy 类型。"""
    import math

    if isinstance(v, float) and math.isnan(v):
        return None
    return v
