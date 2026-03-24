"""vectorbt 批量筛选引擎。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd


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
    details: dict[str, dict] = {}

    for symbol, df in data.items():
        try:
            entries, exits = signal_func(df, **params)
            pf = vbt.Portfolio.from_signals(
                df["Close"],
                entries,
                exits,
                init_cash=cash,
                freq=freq,
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
            print(f"[screening] 跳过 {symbol}: {exc}")

    if details:
        rankings = pd.DataFrame(details).T
        rankings = rankings.sort_values("total_return", ascending=False)
    else:
        rankings = pd.DataFrame()

    return ScreeningResult(rankings=rankings, details=details)
