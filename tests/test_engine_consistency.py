"""验证 backtesting.py 与 vectorbt 的执行结果对齐。"""

from __future__ import annotations

import math

import pandas as pd
import pytest
import vectorbt as vbt

from quant_balance.core.backtest import run_backtest
from quant_balance.core.strategies import SmaCross, sma_cross_signals


def _make_gapless_crossover_df(days: int = 240) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    close = [10 + math.sin(index / 8) * 2 + index * 0.02 for index in range(days)]
    return pd.DataFrame({
        "Open": close,
        "High": close,
        "Low": close,
        "Close": close,
        "Volume": [1_000_000] * days,
    }, index=dates)


def test_backtesting_and_vectorbt_align_on_next_bar_execution():
    df = _make_gapless_crossover_df()

    bt_result = run_backtest(
        df,
        SmaCross,
        cash=100_000.0,
        commission=0.0,
        strategy_params={"fast_period": 5, "slow_period": 20},
    )
    entries, exits = sma_cross_signals(df, fast=5, slow=20)
    entries = entries.shift(1, fill_value=False)
    exits = exits.shift(1, fill_value=False)
    pf = vbt.Portfolio.from_signals(
        df["Close"],
        entries,
        exits,
        init_cash=100_000.0,
        freq="1D",
    )

    assert bt_result.report["trades_count"] == int(pf.stats()["Total Trades"])
    assert bt_result.report["total_return_pct"] == pytest.approx(pf.total_return() * 100, rel=1e-4)


def test_backtesting_and_vectorbt_align_with_risk_exits():
    df = _make_gapless_crossover_df()

    bt_result = run_backtest(
        df,
        SmaCross,
        cash=100_000.0,
        commission=0.0,
        strategy_params={
            "fast_period": 5,
            "slow_period": 20,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.1,
        },
    )
    entries, exits = sma_cross_signals(df, fast=5, slow=20)
    entries = entries.shift(1, fill_value=False)
    exits = exits.shift(1, fill_value=False)
    pf = vbt.Portfolio.from_signals(
        df["Close"],
        entries,
        exits,
        init_cash=100_000.0,
        freq="1D",
        sl_stop=0.05,
        tp_stop=0.1,
    )

    assert bt_result.report["trades_count"] == int(pf.stats()["Total Trades"])
    assert bt_result.report["total_return_pct"] == pytest.approx(pf.total_return() * 100, rel=1e-4)
