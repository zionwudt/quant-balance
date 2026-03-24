"""测试回测服务层编排。"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from quant_balance.core.backtest import BacktestResult
from quant_balance.services.backtest_service import run_optimize, run_single_backtest


def _make_sample_df(days: int = 10) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    close = [10.0 + index * 0.1 for index in range(days)]
    return pd.DataFrame({
        "Open": [value - 0.05 for value in close],
        "High": [value + 0.1 for value in close],
        "Low": [value - 0.1 for value in close],
        "Close": close,
        "Volume": [1_000_000] * days,
    }, index=dates)


def _fake_backtest_result() -> BacktestResult:
    equity_curve = pd.DataFrame({"Equity": [100_000.0, 102_000.0]}, index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
    trades = pd.DataFrame([
        {
            "Size": 100,
            "EntryBar": 0,
            "ExitBar": 1,
            "EntryPrice": 10.0,
            "ExitPrice": 10.2,
            "PnL": 20.0,
            "ReturnPct": 0.02,
            "EntryTime": "2024-01-01 00:00:00",
            "ExitTime": "2024-01-02 00:00:00",
            "Duration": "1 days 00:00:00",
        }
    ])
    return BacktestResult(
        stats=pd.Series({"Return [%]": 2.0}),
        trades=trades,
        equity_curve=equity_curve,
        report={"final_equity": 102_000.0, "trades_count": 1},
    )


def test_run_single_backtest_rejects_unknown_strategy():
    with pytest.raises(ValueError, match="未知策略"):
        run_single_backtest(
            symbol="600519.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            strategy="unknown",
        )


def test_run_single_backtest_returns_api_ready_payload():
    sample_df = _make_sample_df()
    with (
        patch("quant_balance.services.backtest_service.load_dataframe", return_value=sample_df) as mock_load,
        patch("quant_balance.services.backtest_service.run_backtest", return_value=_fake_backtest_result()) as mock_run,
    ):
        result = run_single_backtest(
            symbol="600519.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            strategy="buy_and_hold",
            cash=100_000.0,
            commission=0.001,
            params={"foo": "bar"},
        )

    assert result["summary"]["final_equity"] == 102_000.0
    assert result["run_context"]["bars_count"] == len(sample_df)
    assert result["trades"][0]["pnl"] == 20.0
    assert result["equity_curve"][0]["equity"] == 100_000.0
    mock_load.assert_called_once()
    mock_run.assert_called_once()


def test_run_optimize_requires_param_ranges():
    with pytest.raises(ValueError, match="param_ranges 不能为空"):
        run_optimize(
            symbol="600519.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            param_ranges={},
        )


def test_run_optimize_returns_normalized_output():
    sample_df = _make_sample_df()
    stats = pd.Series({
        "Return [%]": 12.5,
        "Sharpe Ratio": 1.8,
        "# Trades": 6,
    })
    numpy_like_fast = pd.Index([5])[0]
    numpy_like_slow = pd.Index([20])[0]
    with (
        patch("quant_balance.services.backtest_service.load_dataframe", return_value=sample_df) as mock_load,
        patch(
            "quant_balance.services.backtest_service.optimize",
            return_value=(stats, {"fast_period": numpy_like_fast, "slow_period": numpy_like_slow}),
        ) as mock_optimize,
    ):
        result = run_optimize(
            symbol="600519.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            strategy="sma_cross",
            param_ranges={"fast_period": range(5, 10), "slow_period": [20, 30]},
        )

    assert result["best_params"] == {"fast_period": 5, "slow_period": 20}
    assert result["best_stats"]["total_return_pct"] == 12.5
    assert result["run_context"]["param_ranges"] == {"fast_period": [5, 6, 7, 8, 9], "slow_period": [20, 30]}
    mock_load.assert_called_once()
    mock_optimize.assert_called_once()
