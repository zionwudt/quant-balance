"""测试 backtesting.py 回测引擎封装。"""

import pandas as pd

from quant_balance.core.backtest import BacktestResult, run_backtest
from quant_balance.core.strategies import BuyAndHold, SmaCross


def _make_sample_df(days: int = 100) -> pd.DataFrame:
    """生成测试用 OHLCV DataFrame。"""
    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    close = [10.0 + index * 0.1 for index in range(days)]
    return pd.DataFrame({
        "Open": [value - 0.05 for value in close],
        "High": [value + 0.1 for value in close],
        "Low": [value - 0.1 for value in close],
        "Close": close,
        "Volume": [1_000_000] * days,
    }, index=dates)


def test_run_backtest_returns_result():
    df = _make_sample_df()
    result = run_backtest(df, BuyAndHold, cash=100_000.0)

    assert isinstance(result, BacktestResult)
    assert result.report["final_equity"] > 0
    assert result.report["trades_count"] >= 1
    assert not result.equity_curve.empty


def test_run_backtest_sma_cross():
    df = _make_sample_df(200)
    result = run_backtest(df, SmaCross, cash=100_000.0, strategy_params={"fast_period": 5, "slow_period": 20})

    assert isinstance(result, BacktestResult)
    assert "total_return_pct" in result.report
    assert "sharpe_ratio" in result.report


def test_normalize_bt_stats_handles_keys():
    df = _make_sample_df()
    result = run_backtest(df, BuyAndHold)
    report = result.report

    assert "initial_equity" in report
    assert "final_equity" in report
    assert "max_drawdown_pct" in report
    assert "trades_count" in report
