"""组合回测服务 — 编排多标的数据加载与组合引擎执行。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, is_dataclass
from time import perf_counter

from quant_balance.core.data_adapter import load_multi_dataframes
from quant_balance.core.portfolio import run_portfolio_backtest
from quant_balance.data.stock_pool import lookup_stock_metadata
from quant_balance.logging_utils import get_logger, log_event

logger = get_logger(__name__)


def run_portfolio_research(
    *,
    symbols: list[str],
    start_date: str,
    end_date: str,
    allocation: str = "equal",
    weights: dict[str, float] | None = None,
    rebalance_frequency: str = "monthly",
    cash: float = 100_000.0,
    commission: float = 0.001,
    data_provider: str | None = None,
) -> dict:
    """执行组合回测，返回 API 可直接消费的结果字典。"""
    if not symbols:
        raise ValueError("symbols 不能为空")

    started_at = perf_counter()
    load_kwargs = {}
    if data_provider is not None:
        load_kwargs["data_provider"] = data_provider
    data = load_multi_dataframes(symbols, start_date, end_date, **load_kwargs)
    if not data:
        raise ValueError("未加载到任何可用于组合回测的行情数据")

    result = run_portfolio_backtest(
        data,
        allocation=allocation,
        custom_weights=weights,
        rebalance_frequency=rebalance_frequency,
        cash=cash,
        commission=commission,
        symbol_metadata=lookup_stock_metadata(list(data.keys())),
        log_context={
            "start_date": start_date,
            "end_date": end_date,
            "allocation": allocation,
            "rebalance_frequency": rebalance_frequency,
            "data_provider": data_provider,
        },
    )
    loaded_symbols = list(result.close_matrix.columns)
    skipped_symbols = [symbol for symbol in symbols if symbol not in loaded_symbols]

    payload = {
        "summary": _jsonable_value(result.report),
        "equity_curve": _series_to_dicts(result.equity_curve, value_key="equity"),
        "weights": _weights_to_dicts(result.weights),
        "rebalances": _rebalances_to_dicts(result.rebalances),
        "attribution": _jsonable_value(result.attribution),
        "run_context": {
            "symbols": symbols,
            "loaded_symbols": loaded_symbols,
            "skipped_symbols": skipped_symbols,
            "start_date": start_date,
            "end_date": end_date,
            "allocation": allocation,
            "weights": weights or {},
            "rebalance_frequency": rebalance_frequency,
            "cash": cash,
            "commission": commission,
            "data_provider": data_provider,
            "bars_count": len(result.close_matrix),
        },
    }
    log_event(
        logger,
        "PORTFOLIO_RUN",
        stage="service",
        symbols=symbols,
        loaded_symbols=loaded_symbols,
        skipped_symbols=skipped_symbols,
        start_date=start_date,
        end_date=end_date,
        allocation=allocation,
        rebalance_frequency=rebalance_frequency,
        cash=cash,
        commission=commission,
        data_provider=data_provider,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
    )
    return payload


def _jsonable_value(value: object) -> object:
    if is_dataclass(value):
        return {
            key: _jsonable_value(item)
            for key, item in asdict(value).items()
        }
    if isinstance(value, dict):
        return {key: _jsonable_value(item) for key, item in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return [_jsonable_value(item) for item in value]

    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except (TypeError, ValueError):
            return value
    return value


def _series_to_dicts(series, *, value_key: str) -> list[dict]:
    if series is None or len(series) == 0:
        return []
    return [
        {"date": str(index), value_key: float(value)}
        for index, value in series.items()
    ]


def _weights_to_dicts(weights_df) -> list[dict]:
    if weights_df is None or weights_df.empty:
        return []
    records = []
    for index, row in weights_df.iterrows():
        records.append({
            "date": str(index),
            "weights": {column: float(value) for column, value in row.fillna(0.0).items()},
        })
    return records


def _rebalances_to_dicts(rebalances_df) -> list[dict]:
    if rebalances_df is None or rebalances_df.empty:
        return []
    records = []
    for index, row in rebalances_df.iterrows():
        weights = {
            column: float(value)
            for column, value in row.items()
            if column != "turnover_pct"
        }
        records.append({
            "date": str(index),
            "turnover_pct": float(row.get("turnover_pct", 0.0)),
            "weights": weights,
        })
    return records
