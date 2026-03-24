"""回测服务 — 编排数据加载与引擎执行。"""

from __future__ import annotations

from collections.abc import Iterable
from time import perf_counter

from quant_balance.core.backtest import optimize, run_backtest
from quant_balance.core.report import bt_trades_to_dicts, equity_curve_to_dicts, normalize_bt_stats
from quant_balance.core.strategies import STRATEGY_REGISTRY
from quant_balance.data import load_dataframe
from quant_balance.logging_utils import get_logger, log_event

logger = get_logger(__name__)


def run_single_backtest(
    *,
    symbol: str,
    start_date: str,
    end_date: str,
    strategy: str = "sma_cross",
    cash: float = 100_000.0,
    commission: float = 0.001,
    params: dict | None = None,
    data_provider: str | None = None,
) -> dict:
    """执行单股精细回测，返回 API 可直接消费的结果字典。"""
    strategy_cls = STRATEGY_REGISTRY.get(strategy)
    if strategy_cls is None:
        raise ValueError(f"未知策略: {strategy}，可用: {list(STRATEGY_REGISTRY)}")

    started_at = perf_counter()
    load_kwargs = {"adjust": "qfq"}
    if data_provider is not None:
        load_kwargs["provider"] = data_provider
    df = load_dataframe(symbol, start_date, end_date, **load_kwargs)

    result = run_backtest(
        df, strategy_cls,
        cash=cash, commission=commission,
        strategy_params=params,
        log_context={
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "strategy": strategy,
            "data_provider": df.attrs.get("data_provider", data_provider),
        },
    )

    payload = {
        "summary": result.report,
        "trades": bt_trades_to_dicts(result.trades, params),
        "equity_curve": equity_curve_to_dicts(result.equity_curve),
        "run_context": {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "strategy": strategy,
            "cash": cash,
            "commission": commission,
            "params": params or {},
            "bars_count": len(df),
            "data_provider": df.attrs.get("data_provider", data_provider),
        },
    }
    log_event(
        logger,
        "BACKTEST_RUN",
        stage="service",
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        strategy=strategy,
        cash=cash,
        commission=commission,
        params=params or {},
        bars_count=len(df),
        trades_count=len(result.trades),
        data_provider=df.attrs.get("data_provider", data_provider),
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
    )
    return payload


def run_optimize(
    *,
    symbol: str,
    start_date: str,
    end_date: str,
    strategy: str = "sma_cross",
    cash: float = 100_000.0,
    commission: float = 0.001,
    maximize: str = "Sharpe Ratio",
    param_ranges: dict | None = None,
    data_provider: str | None = None,
) -> dict:
    """执行参数优化，返回最优参数和统计。"""
    strategy_cls = STRATEGY_REGISTRY.get(strategy)
    if strategy_cls is None:
        raise ValueError(f"未知策略: {strategy}，可用: {list(STRATEGY_REGISTRY)}")

    if not param_ranges:
        raise ValueError("param_ranges 不能为空")

    started_at = perf_counter()
    load_kwargs = {"adjust": "qfq"}
    if data_provider is not None:
        load_kwargs["provider"] = data_provider
    df = load_dataframe(symbol, start_date, end_date, **load_kwargs)

    stats, best_params = optimize(
        df, strategy_cls,
        cash=cash, commission=commission,
        maximize=maximize,
        log_context={
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "strategy": strategy,
            "data_provider": df.attrs.get("data_provider", data_provider),
        },
        **param_ranges,
    )

    payload = {
        "best_params": _jsonable_value(best_params),
        "best_stats": normalize_bt_stats(stats),
        "run_context": {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "strategy": strategy,
            "maximize": maximize,
            "param_ranges": _jsonable_value(param_ranges),
            "data_provider": df.attrs.get("data_provider", data_provider),
        },
    }
    log_event(
        logger,
        "BACKTEST_OPTIMIZE",
        stage="service",
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        strategy=strategy,
        maximize=maximize,
        param_ranges=_jsonable_value(param_ranges),
        best_params=_jsonable_value(best_params),
        data_provider=df.attrs.get("data_provider", data_provider),
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
    )
    return payload


def _jsonable_value(value: object) -> object:
    """递归清理 numpy/pandas 标量与可迭代对象，确保可 JSON 序列化。"""
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
