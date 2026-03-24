"""backtesting.py 回测引擎封装。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
from backtesting import Backtest, Strategy

from quant_balance.core.report import normalize_bt_stats


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
    stats = bt.run(**(strategy_params or {}))
    return BacktestResult(
        stats=stats,
        trades=stats["_trades"],
        equity_curve=stats["_equity_curve"],
        report=normalize_bt_stats(stats),
    )


def optimize(
    df: pd.DataFrame,
    strategy_cls: type[Strategy],
    *,
    cash: float = 100_000.0,
    commission: float = 0.001,
    maximize: str = "Sharpe Ratio",
    constraint: Callable[[object], bool] | None = None,
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
    stats = bt.optimize(**kwargs)
    best_params = {
        key: getattr(stats["_strategy"], key, None)
        for key in param_ranges
    }
    return stats, best_params
