"""vectorbt 组合回测引擎。"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Literal

import pandas as pd

from quant_balance.core.attribution import (
    AttributionReport,
    DEFAULT_BENCHMARK_LABEL,
    build_portfolio_attribution,
)
from quant_balance.core.report import normalize_vbt_stats
from quant_balance.logging_utils import get_logger, log_event

logger = get_logger(__name__)

RebalanceFrequency = Literal["daily", "weekly", "monthly", "quarterly"]
AllocationMode = Literal["equal", "custom"]


@dataclass(slots=True)
class PortfolioBacktestResult:
    """组合回测结果。"""

    stats: pd.Series
    equity_curve: pd.Series
    weights: pd.DataFrame
    rebalances: pd.DataFrame
    report: dict
    close_matrix: pd.DataFrame
    attribution: AttributionReport


def run_portfolio_backtest(
    data: dict[str, pd.DataFrame],
    *,
    allocation: AllocationMode = "equal",
    custom_weights: dict[str, float] | None = None,
    rebalance_frequency: RebalanceFrequency = "monthly",
    cash: float = 100_000.0,
    commission: float = 0.001,
    symbol_metadata: dict[str, dict[str, str]] | None = None,
    benchmark_label: str = DEFAULT_BENCHMARK_LABEL,
    log_context: dict[str, object] | None = None,
) -> PortfolioBacktestResult:
    """执行组合回测。"""
    import vectorbt as vbt

    if not data:
        raise ValueError("组合回测至少需要 1 只股票")

    close_matrix = _build_close_matrix(data)
    target_weights = build_target_weights(
        close_matrix,
        allocation=allocation,
        custom_weights=custom_weights,
        rebalance_frequency=rebalance_frequency,
    )
    effective_weights = target_weights.ffill().fillna(0.0)
    rebalances = build_rebalance_log(target_weights)
    benchmark_weights = build_benchmark_weights(close_matrix)

    started_at = perf_counter()
    pf = vbt.Portfolio.from_orders(
        close_matrix,
        size=target_weights,
        size_type="targetpercent",
        init_cash=cash,
        fees=commission,
        cash_sharing=True,
        group_by=True,
        call_seq="auto",
        freq="1D",
    )
    benchmark_pf = vbt.Portfolio.from_orders(
        close_matrix,
        size=benchmark_weights,
        size_type="targetpercent",
        init_cash=cash,
        fees=commission,
        cash_sharing=True,
        group_by=True,
        call_seq="auto",
        freq="1D",
    )
    equity_curve = pf.value()
    stats = pf.stats()
    report = normalize_vbt_stats(
        stats,
        equity_curve,
        initial_equity=cash,
    )
    report.update({
        "symbols_count": len(close_matrix.columns),
        "allocation": allocation,
        "rebalance_frequency": rebalance_frequency,
        "rebalance_count": len(rebalances),
    })
    attribution = build_portfolio_attribution(
        close_matrix=close_matrix,
        portfolio=pf,
        benchmark=benchmark_pf,
        initial_cash=cash,
        symbol_metadata=symbol_metadata,
        benchmark_label=benchmark_label,
    )
    log_fields = {
        "stage": "engine",
        "allocation": allocation,
        "rebalance_frequency": rebalance_frequency,
        "symbols_count": len(close_matrix.columns),
        "bars_count": len(close_matrix),
        "cash": cash,
        "commission": commission,
        "rebalance_count": len(rebalances),
        "duration_ms": round((perf_counter() - started_at) * 1000, 2),
    }
    log_fields.update(log_context or {})
    log_event(logger, "PORTFOLIO_RUN", **log_fields)
    return PortfolioBacktestResult(
        stats=stats,
        equity_curve=equity_curve,
        weights=effective_weights,
        rebalances=rebalances,
        report=report,
        close_matrix=close_matrix,
        attribution=attribution,
    )


def build_target_weights(
    close_matrix: pd.DataFrame,
    *,
    allocation: AllocationMode,
    custom_weights: dict[str, float] | None,
    rebalance_frequency: RebalanceFrequency,
) -> pd.DataFrame:
    """构造目标权重矩阵。"""
    symbols = list(close_matrix.columns)
    base_weights = _resolve_base_weights(symbols, allocation, custom_weights)
    rebalance_mask = _build_rebalance_mask(close_matrix.index, rebalance_frequency)

    target_weights = pd.DataFrame(index=close_matrix.index, columns=symbols, dtype=float)
    target_weights.loc[rebalance_mask.to_numpy(), :] = base_weights.to_numpy()
    return target_weights


def build_rebalance_log(target_weights: pd.DataFrame) -> pd.DataFrame:
    """生成调仓记录。"""
    rebalance_rows = target_weights.dropna(how="all").fillna(0.0)
    if rebalance_rows.empty:
        return pd.DataFrame(columns=["turnover_pct", *target_weights.columns])

    previous = pd.Series(0.0, index=target_weights.columns, dtype=float)
    records: list[dict[str, object]] = []
    for date, row in rebalance_rows.iterrows():
        current = row.astype(float)
        turnover = _turnover_from_weights(previous, current)
        records.append({
            "date": date,
            "turnover_pct": turnover * 100,
            **current.to_dict(),
        })
        previous = current

    return pd.DataFrame(records).set_index("date")


def build_benchmark_weights(close_matrix: pd.DataFrame) -> pd.DataFrame:
    """构造首日等权买入并持有的基准权重。"""

    weight = 1 / len(close_matrix.columns)
    weights = pd.DataFrame(index=close_matrix.index, columns=close_matrix.columns, dtype=float)
    weights.iloc[0] = weight
    return weights


def _build_close_matrix(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    close_matrix = pd.concat(
        {symbol: frame["Close"] for symbol, frame in data.items()},
        axis=1,
    ).sort_index()
    close_matrix = close_matrix.dropna(how="any")
    if close_matrix.empty:
        raise ValueError("无法构造对齐后的收盘价宽表，请检查样本区间和股票列表")
    return close_matrix


def _resolve_base_weights(
    symbols: list[str],
    allocation: AllocationMode,
    custom_weights: dict[str, float] | None,
) -> pd.Series:
    if allocation == "equal":
        weight = 1 / len(symbols)
        return pd.Series({symbol: weight for symbol in symbols}, dtype=float)

    if allocation != "custom":
        raise ValueError(f"不支持的 allocation: {allocation}")
    if not custom_weights:
        raise ValueError("allocation=custom 时必须提供 weights")

    unknown_symbols = set(custom_weights) - set(symbols)
    if unknown_symbols:
        raise ValueError(f"weights 包含未知股票: {sorted(unknown_symbols)}")

    weights = pd.Series(
        {symbol: float(custom_weights.get(symbol, 0.0)) for symbol in symbols},
        dtype=float,
    )
    if (weights < 0).any():
        raise ValueError("weights 不能包含负数")
    total = float(weights.sum())
    if total <= 0:
        raise ValueError("weights 总和必须 > 0")
    return weights / total


def _build_rebalance_mask(index: pd.Index, rebalance_frequency: RebalanceFrequency) -> pd.Series:
    series = pd.Series(False, index=index, dtype=bool)
    if len(index) == 0:
        return series

    if rebalance_frequency == "daily":
        return pd.Series(True, index=index, dtype=bool)
    if rebalance_frequency == "weekly":
        period = index.to_period("W")
    elif rebalance_frequency == "monthly":
        period = index.to_period("M")
    elif rebalance_frequency == "quarterly":
        period = index.to_period("Q")
    else:
        raise ValueError(f"不支持的 rebalance_frequency: {rebalance_frequency}")

    series.iloc[0] = True
    series.iloc[1:] = period[1:] != period[:-1]
    return series


def _turnover_from_weights(previous: pd.Series, current: pd.Series) -> float:
    if previous.sum() == 0:
        return float(current.abs().sum())
    return float((current - previous).abs().sum() / 2)
