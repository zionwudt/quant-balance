"""测试 backtesting.py 回测引擎封装。"""

import logging

import pandas as pd
import pytest

from quant_balance.core.backtest import BacktestResult, run_backtest
from quant_balance.core.strategies import BuyAndHold, DcaStrategy, SmaCross


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


def test_run_backtest_dca_uses_incremental_orders():
    df = _make_sample_df(80)
    result = run_backtest(
        df,
        DcaStrategy,
        cash=100_000.0,
        strategy_params={"interval_days": 20, "trade_fraction": 0.2},
    )

    assert isinstance(result, BacktestResult)
    assert result.report["trades_count"] >= 3
    assert len(result.trades) >= 3


def test_run_backtest_exposes_risk_exit_summary():
    df = pd.DataFrame({
        "Open": [100.0, 100.0, 100.0, 94.0, 93.0, 92.0],
        "High": [100.0, 100.0, 100.0, 94.0, 93.0, 92.0],
        "Low": [100.0, 100.0, 100.0, 94.0, 93.0, 92.0],
        "Close": [100.0, 100.0, 100.0, 94.0, 93.0, 92.0],
        "Volume": [1_000_000] * 6,
    }, index=pd.date_range("2024-01-01", periods=6, freq="B"))
    result = run_backtest(
        df,
        BuyAndHold,
        strategy_params={"stop_loss_pct": 0.05, "take_profit_pct": 0.2},
    )

    assert result.report["stop_loss_pct"] == 0.05
    assert result.report["take_profit_pct"] == 0.2
    assert "stop_loss_trades" in result.report
    assert "take_profit_trades" in result.report


def test_normalize_bt_stats_handles_keys():
    df = _make_sample_df()
    result = run_backtest(df, BuyAndHold)
    report = result.report

    assert "initial_equity" in report
    assert "final_equity" in report
    assert "max_drawdown_pct" in report
    assert "trades_count" in report


def test_run_backtest_emits_structured_log(caplog: pytest.LogCaptureFixture):
    df = _make_sample_df()
    caplog.set_level(logging.INFO, logger="quant_balance")

    run_backtest(
        df,
        BuyAndHold,
        log_context={
            "symbol": "AAA",
            "start_date": "2024-01-01",
            "end_date": "2024-05-31",
            "strategy": "buy_and_hold",
            "data_provider": "tushare",
        },
    )

    records = [
        record for record in caplog.records
        if getattr(record, "qb_event", None) == "BACKTEST_RUN"
    ]
    assert len(records) == 1
    payload = records[0].qb_payload
    assert payload["stage"] == "engine"
    assert payload["strategy"] == "buy_and_hold"
    assert payload["symbol"] == "AAA"
    assert payload["bars_count"] == len(df)
