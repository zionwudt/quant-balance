"""backtesting.py 回测引擎封装。

封装了 backtesting.py 库的 Backtest 和 Strategy 接口，提供：
- run_backtest(): 单股精细回测
- optimize(): 参数优化与 Walk-Forward 分析

核心概念：
- Strategy: 策略类，需实现 init() 和 next() 方法
- stats: 回测统计结果（pandas.Series）
- trades: 交易记录（pandas.DataFrame）
- equity_curve: 权益曲线
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from time import perf_counter

import pandas as pd
from backtesting import Backtest, Strategy

from quant_balance.core.report import normalize_bt_stats
from quant_balance.logging_utils import get_logger, log_event

logger = get_logger(__name__)


@dataclass(slots=True)
class BacktestResult:
    """单股精细回测结果。"""

    stats: pd.Series
    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    report: dict


@dataclass(slots=True)
class OptimizeResult:
    """参数优化结果。"""

    best_stats: pd.Series
    best_params: dict[str, object]
    top_results: list[dict[str, object]] = field(default_factory=list)
    candidate_count: int = 0


def run_backtest(
    df: pd.DataFrame,
    strategy_cls: type[Strategy],
    *,
    cash: float = 100_000.0,
    spread: float = 0.0,
    commission: float = 0.001,
    exclusive_orders: bool | None = None,
    finalize_trades: bool = True,
    strategy_params: dict | None = None,
    log_context: dict[str, object] | None = None,
) -> BacktestResult:
    """执行单股回测，返回标准化结果。"""
    resolved_exclusive_orders = _resolve_exclusive_orders(
        strategy_cls, exclusive_orders
    )
    bt = Backtest(
        df,
        strategy_cls,
        cash=cash,
        spread=spread,
        commission=commission,
        exclusive_orders=resolved_exclusive_orders,
        finalize_trades=finalize_trades,
    )
    started_at = perf_counter()
    stats = bt.run(**(strategy_params or {}))
    result = BacktestResult(
        stats=stats,
        trades=stats["_trades"],
        equity_curve=stats["_equity_curve"],
        report=normalize_bt_stats(stats, risk_params=strategy_params),
    )
    log_fields = {
        "stage": "engine",
        "strategy": getattr(strategy_cls, "__name__", str(strategy_cls)),
        "bars_count": len(df),
        "cash": cash,
        "spread": spread,
        "commission": commission,
        "exclusive_orders": resolved_exclusive_orders,
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
    exclusive_orders: bool | None = None,
    maximize: str = "Sharpe Ratio",
    constraint: Callable[[object], bool] | None = None,
    top_n: int = 5,
    log_context: dict[str, object] | None = None,
    **param_ranges,
) -> OptimizeResult:
    """参数优化，返回最优组合与排名结果。"""
    if top_n < 1:
        raise ValueError("top_n 必须 >= 1")

    resolved_exclusive_orders = _resolve_exclusive_orders(
        strategy_cls, exclusive_orders
    )
    bt = Backtest(
        df,
        strategy_cls,
        cash=cash,
        commission=commission,
        exclusive_orders=resolved_exclusive_orders,
        finalize_trades=True,
    )
    kwargs: dict = {
        **param_ranges,
        "maximize": maximize,
        "return_heatmap": True,
    }
    if constraint is not None:
        kwargs["constraint"] = constraint
    started_at = perf_counter()
    stats, heatmap = bt.optimize(**kwargs)
    best_params = {key: getattr(stats["_strategy"], key, None) for key in param_ranges}
    top_results = _rank_optimization_candidates(bt, heatmap, top_n)
    log_fields = {
        "stage": "engine",
        "strategy": getattr(strategy_cls, "__name__", str(strategy_cls)),
        "bars_count": len(df),
        "cash": cash,
        "commission": commission,
        "exclusive_orders": resolved_exclusive_orders,
        "maximize": maximize,
        "param_ranges": param_ranges,
        "best_params": best_params,
        "top_n": top_n,
        "candidate_count": len(heatmap),
        "duration_ms": round((perf_counter() - started_at) * 1000, 2),
    }
    log_fields.update(log_context or {})
    log_event(logger, "BACKTEST_OPTIMIZE", **log_fields)
    return OptimizeResult(
        best_stats=stats,
        best_params=best_params,
        top_results=top_results,
        candidate_count=len(heatmap),
    )


def _resolve_exclusive_orders(
    strategy_cls: type[Strategy],
    override: bool | None,
) -> bool:
    if override is not None:
        return override
    return bool(getattr(strategy_cls, "qb_exclusive_orders", True))


def _rank_optimization_candidates(
    bt: Backtest,
    heatmap: pd.Series,
    top_n: int,
) -> list[dict[str, object]]:
    ranked = heatmap.dropna().sort_values(ascending=False).head(top_n)
    if ranked.empty:
        return []

    top_results: list[dict[str, object]] = []
    index_names = list(heatmap.index.names)
    for rank, (key, score) in enumerate(ranked.items(), start=1):
        values = key if isinstance(key, tuple) else (key,)
        params = dict(zip(index_names, values, strict=False))
        candidate_stats = bt.run(**params)
        top_results.append(
            {
                "rank": rank,
                "score": float(score),
                "params": params,
                "stats": normalize_bt_stats(candidate_stats, risk_params=params),
            }
        )
    return top_results
