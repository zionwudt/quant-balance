"""批量筛选服务 — 编排 stock_pool + vectorbt 筛选。"""

from __future__ import annotations

from quant_balance.core.data_adapter import load_multi_dataframes
from quant_balance.core.screening import run_screening
from quant_balance.core.strategies import SIGNAL_REGISTRY
from quant_balance.data.stock_pool import get_pool_at_date


def run_stock_screening(
    *,
    pool_date: str,
    start_date: str,
    end_date: str,
    signal: str = "sma_cross",
    signal_params: dict | None = None,
    top_n: int = 20,
    cash: float = 100_000.0,
    symbols: list[str] | None = None,
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

    if symbols is None:
        symbols = get_pool_at_date(pool_date)

    data = load_multi_dataframes(symbols, start_date, end_date)
    if not data:
        return {
            "rankings": [],
            "total_screened": 0,
            "run_context": {
                "pool_date": pool_date,
                "start_date": start_date,
                "end_date": end_date,
                "signal": signal,
            },
        }

    result = run_screening(
        data, signal_func,
        cash=cash,
        signal_params=signal_params,
    )

    rankings_list = []
    if not result.rankings.empty:
        top = result.rankings.head(top_n)
        for symbol, row in top.iterrows():
            rankings_list.append({
                "symbol": symbol,
                **{k: _safe_value(v) for k, v in row.to_dict().items()},
            })

    return {
        "rankings": rankings_list,
        "total_screened": len(data),
        "run_context": {
            "pool_date": pool_date,
            "start_date": start_date,
            "end_date": end_date,
            "signal": signal,
            "signal_params": signal_params or {},
            "top_n": top_n,
        },
    }


def _safe_value(v: object) -> object:
    """处理 NaN 和 numpy 类型。"""
    import math

    if isinstance(v, float) and math.isnan(v):
        return None
    return v
