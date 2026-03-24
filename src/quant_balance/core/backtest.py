"""backtesting.py 回测引擎封装。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter

import pandas as pd
from backtesting import Backtest, Strategy

from quant_balance.logging_utils import get_logger, log_event
from quant_balance.core.report import normalize_bt_stats

logger = get_logger(__name__)


@dataclass(slots=True)
class BacktestResult:
    """单股精细回测结果。"""

    stats: pd.Series
    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    report: dict


def run_backtest(
    df: pd.DataFrame,
    strategy_cls: type[Strategy],
    *,
    cash: float = 100_000.0,
    commission: float = 0.001,
    exclusive_orders: bool = True,
    finalize_trades: bool = True,
    strategy_params: dict | None = None,
    log_context: dict[str, object] | None = None,
) -> BacktestResult:
    """执行单股回测，返回标准化结果。"""
    bt = Backtest(
        df,
        strategy_cls,
        cash=cash,
        commission=commission,
        exclusive_orders=exclusive_orders,
        finalize_trades=finalize_trades,
    )
    started_at = perf_counter()
    stats = bt.run(**(strategy_params or {}))
    result = BacktestResult(
        stats=stats,
        trades=stats["_trades"],
        equity_curve=stats["_equity_curve"],
        report=normalize_bt_stats(stats),
    )
    log_fields = {
        "stage": "engine",
        "strategy": getattr(strategy_cls, "__name__", str(strategy_cls)),
        "bars_count": len(df),
        "cash": cash,
        "commission": commission,
        "params": strategy_params or {},
        "trades_count": len(result.trades),
        "duration_ms": round((perf_counter() - started_at) * 1000, 2),
    }
    log_fields.update(log_context or {})
    log_event(logger, "BACKTEST_RUN", **log_fields)
    return result


def optimize(
    df: pd.DataFrame,
    strategy_cls: type[Strategy],
    *,
    cash: float = 100_000.0,
    commission: float = 0.001,
    maximize: str = "Sharpe Ratio",
    constraint: Callable[[object], bool] | None = None,
    log_context: dict[str, object] | None = None,
    **param_ranges,
) -> tuple[pd.Series, dict]:
    """参数优化，返回 (best_stats, best_params)。"""
    bt = Backtest(
        df,
        strategy_cls,
        cash=cash,
        commission=commission,
        exclusive_orders=True,
        finalize_trades=True,
    )
    kwargs: dict = {**param_ranges, "maximize": maximize}
    if constraint is not None:
        kwargs["constraint"] = constraint
    started_at = perf_counter()
    stats = bt.optimize(**kwargs)
    best_params = {
        key: getattr(stats["_strategy"], key, None)
        for key in param_ranges
    }
    log_fields = {
        "stage": "engine",
        "strategy": getattr(strategy_cls, "__name__", str(strategy_cls)),
        "bars_count": len(df),
        "cash": cash,
        "commission": commission,
        "maximize": maximize,
        "param_ranges": param_ranges,
        "best_params": best_params,
        "duration_ms": round((perf_counter() - started_at) * 1000, 2),
    }
    log_fields.update(log_context or {})
    log_event(logger, "BACKTEST_OPTIMIZE", **log_fields)
    return stats, best_params
