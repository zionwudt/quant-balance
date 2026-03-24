"""vectorbt 批量筛选引擎。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from time import perf_counter

import pandas as pd

from quant_balance.logging_utils import get_logger, log_event

logger = get_logger(__name__)

RISK_PARAM_KEYS = {"stop_loss_pct", "take_profit_pct"}

@dataclass(slots=True)
class ScreeningResult:
    """批量筛选结果。"""

    rankings: pd.DataFrame
    details: dict[str, dict]


def run_screening(
    data: dict[str, pd.DataFrame],
    signal_func: Callable[[pd.DataFrame], tuple[pd.Series, pd.Series]],
    *,
    cash: float = 100_000.0,
    freq: str = "1D",
    signal_params: dict | None = None,
    log_context: dict[str, object] | None = None,
) -> ScreeningResult:
    """对多只股票执行批量回测筛选。

    参数:
    - data: {symbol: OHLCV DataFrame}
    - signal_func: 信号函数 (df, **params) → (entries, exits)
    - cash: 初始资金
    - signal_params: 传给 signal_func 的额外参数
    """
    import vectorbt as vbt

    params = signal_params or {}
    signal_call_params = {
        key: value for key, value in params.items()
        if key not in RISK_PARAM_KEYS
    }
    portfolio_kwargs = _resolve_portfolio_kwargs(signal_func, params)
    details: dict[str, dict] = {}
    failed_symbols: list[str] = []
    started_at = perf_counter()

    for symbol, df in data.items():
        try:
            entries, exits = signal_func(df, **signal_call_params)
            pf = vbt.Portfolio.from_signals(
                df["Close"],
                entries,
                exits,
                init_cash=cash,
                freq=freq,
                **portfolio_kwargs,
            )
            stats = pf.stats()
            details[symbol] = {
                "total_return": pf.total_return(),
                "sharpe_ratio": stats.get("Sharpe Ratio", None),
                "max_drawdown": stats.get("Max Drawdown [%]", None),
                "total_trades": stats.get("Total Trades", 0),
                "win_rate": stats.get("Win Rate [%]", None),
                "profit_factor": stats.get("Profit Factor", None),
                "final_value": pf.final_value(),
            }
        except Exception as exc:  # noqa: BLE001
            failed_symbols.append(symbol)
            log_fields = {
                "symbol": symbol,
                "signal": getattr(signal_func, "__name__", str(signal_func)),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            log_fields.update(log_context or {})
            log_event(
                logger,
                "SCREENING_SYMBOL_SKIP",
                level=logging.WARNING,
                **log_fields,
            )

    if details:
        rankings = pd.DataFrame(details).T
        rankings = rankings.sort_values("total_return", ascending=False)
    else:
        rankings = pd.DataFrame()

    log_fields = {
        "stage": "engine",
        "signal": getattr(signal_func, "__name__", str(signal_func)),
        "signal_params": params,
        "cash": cash,
        "freq": freq,
        "symbols_count": len(data),
        "total_screened": len(details),
        "skipped_count": len(failed_symbols),
        "ranked_count": len(rankings),
        "duration_ms": round((perf_counter() - started_at) * 1000, 2),
    }
    log_fields.update(log_context or {})
    log_event(logger, "SCREENING_RUN", **log_fields)
    return ScreeningResult(rankings=rankings, details=details)


def _resolve_portfolio_kwargs(
    signal_func: Callable[[pd.DataFrame], tuple[pd.Series, pd.Series]],
    params: dict[str, object],
) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    builder = getattr(signal_func, "qb_portfolio_kwargs", None)
    if callable(builder):
        kwargs.update(dict(builder(params)))

    stop_loss_pct = _optional_positive_float(params.get("stop_loss_pct"))
    take_profit_pct = _optional_positive_float(params.get("take_profit_pct"))
    if stop_loss_pct is not None:
        if stop_loss_pct >= 1:
            raise ValueError("stop_loss_pct 必须位于 [0, 1) 区间")
        kwargs["sl_stop"] = stop_loss_pct
    if take_profit_pct is not None:
        kwargs["tp_stop"] = take_profit_pct
    return kwargs


def _optional_positive_float(value: object) -> float | None:
    if value in (None, "", 0, 0.0):
        return None
    number = float(value)
    if number < 0:
        raise ValueError("风险退出比例必须 >= 0")
    return number
