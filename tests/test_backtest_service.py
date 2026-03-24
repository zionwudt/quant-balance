"""测试回测服务层编排。"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pandas as pd
import pytest

from quant_balance.core.backtest import BacktestResult, OptimizeResult
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


def _fake_optimize_result(
    *,
    best_params: dict | None = None,
    total_return_pct: float = 12.5,
    sharpe_ratio: float = 1.8,
    candidate_count: int = 6,
    top_results: list[dict] | None = None,
) -> OptimizeResult:
    params = best_params or {"fast_period": 5, "slow_period": 20}
    return OptimizeResult(
        best_stats=pd.Series({
            "Return [%]": total_return_pct,
            "Sharpe Ratio": sharpe_ratio,
            "# Trades": 6,
        }),
        best_params=params,
        top_results=top_results or [
            {
                "rank": 1,
                "score": sharpe_ratio,
                "params": params,
                "stats": {
                    "total_return_pct": total_return_pct,
                    "sharpe_ratio": sharpe_ratio,
                },
            }
        ],
        candidate_count=candidate_count,
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
    with (
        patch("quant_balance.services.backtest_service.load_dataframe", return_value=sample_df) as mock_load,
        patch(
            "quant_balance.services.backtest_service.optimize",
            return_value=_fake_optimize_result(
                best_params={
                    "fast_period": pd.Index([5])[0],
                    "slow_period": pd.Index([20])[0],
                }
            ),
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
    assert result["top_results"][0]["rank"] == 1
    assert result["execution"]["candidate_count"] == 6
    assert result["execution"]["estimated_total_runs"] == 6
    assert result["run_context"]["param_ranges"] == {"fast_period": [5, 6, 7, 8, 9], "slow_period": [20, 30]}
    assert result["run_context"]["top_n"] == 5
    mock_load.assert_called_once()
    mock_optimize.assert_called_once()


def test_run_optimize_rejects_unknown_param_name():
    with pytest.raises(ValueError, match="未知参数"):
        run_optimize(
            symbol="600519.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            strategy="sma_cross",
            param_ranges={"unknown": [1, 2, 3]},
        )


def test_run_optimize_rejects_unknown_constraint_param():
    with pytest.raises(ValueError, match="constraints 引用了未知参数"):
        run_optimize(
            symbol="600519.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            strategy="sma_cross",
            param_ranges={"fast_period": [5, 6], "slow_period": [20, 30]},
            constraints=[{"left": "fast_period", "operator": "<", "right_param": "missing"}],
        )


def test_run_optimize_returns_walk_forward_payload():
    sample_df = _make_sample_df(days=20)
    with (
        patch("quant_balance.services.backtest_service.load_dataframe", return_value=sample_df),
        patch(
            "quant_balance.services.backtest_service.optimize",
            side_effect=[
                _fake_optimize_result(candidate_count=4),
                _fake_optimize_result(best_params={"fast_period": 4, "slow_period": 18}, candidate_count=4),
                _fake_optimize_result(best_params={"fast_period": 5, "slow_period": 20}, candidate_count=4),
            ],
        ) as mock_optimize,
        patch(
            "quant_balance.services.backtest_service.run_backtest",
            side_effect=[
                _fake_backtest_result(),
                BacktestResult(
                    stats=pd.Series({"Return [%]": -1.0}),
                    trades=pd.DataFrame(),
                    equity_curve=pd.DataFrame({"Equity": [100_000.0, 99_000.0]}),
                    report={"final_equity": 99_000.0, "trades_count": 0},
                ),
            ],
        ) as mock_run_backtest,
    ):
        result = run_optimize(
            symbol="600519.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            strategy="sma_cross",
            maximize="Sharpe Ratio",
            param_ranges={"fast_period": [4, 5], "slow_period": [18, 20]},
            top_n=3,
            constraints=[{"left": "fast_period", "operator": "<", "right_param": "slow_period"}],
            walk_forward={"train_bars": 10, "test_bars": 5, "step_bars": 5},
        )

    assert result["walk_forward"]["windows_count"] == 2
    assert len(result["walk_forward"]["windows"]) == 2
    assert result["walk_forward"]["windows"][0]["in_sample"]["total_return_pct"] == 12.5
    assert result["walk_forward"]["windows"][0]["out_of_sample"]["final_equity"] == 102_000.0
    assert result["walk_forward"]["averages"]["out_of_sample"]["windows_count"] == 2
    assert result["execution"]["estimated_total_runs"] == 12
    assert mock_optimize.call_count == 3
    assert mock_optimize.call_args_list[0].kwargs["top_n"] == 3
    assert mock_optimize.call_args_list[1].kwargs["top_n"] == 1
    assert callable(mock_optimize.call_args_list[0].kwargs["constraint"])
    assert mock_run_backtest.call_count == 2


def test_run_single_backtest_passes_data_provider():
    sample_df = _make_sample_df()
    sample_df.attrs["data_provider"] = "akshare"
    sample_df.attrs["asset_type"] = "stock"
    with (
        patch("quant_balance.services.backtest_service.load_dataframe", return_value=sample_df) as mock_load,
        patch("quant_balance.services.backtest_service.run_backtest", return_value=_fake_backtest_result()),
    ):
        result = run_single_backtest(
            symbol="600519.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            data_provider="akshare",
        )

    assert result["run_context"]["data_provider"] == "akshare"
    mock_load.assert_called_once_with(
        "600519.SH",
        "2024-01-01",
        "2024-06-30",
        asset_type="stock",
        adjust="qfq",
        provider="akshare",
    )


def test_run_single_backtest_passes_convertible_bond_asset_type():
    sample_df = _make_sample_df()
    sample_df.attrs["data_provider"] = "tushare"
    sample_df.attrs["asset_type"] = "convertible_bond"
    with (
        patch("quant_balance.services.backtest_service.load_dataframe", return_value=sample_df) as mock_load,
        patch("quant_balance.services.backtest_service.run_backtest", return_value=_fake_backtest_result()),
    ):
        result = run_single_backtest(
            symbol="110043.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            asset_type="convertible_bond",
        )

    assert result["run_context"]["asset_type"] == "convertible_bond"
    mock_load.assert_called_once_with(
        "110043.SH",
        "2024-01-01",
        "2024-06-30",
        asset_type="convertible_bond",
        adjust="qfq",
    )


def test_run_optimize_emits_structured_log(caplog: pytest.LogCaptureFixture):
    sample_df = _make_sample_df()
    sample_df.attrs["data_provider"] = "tushare"
    caplog.set_level(logging.INFO, logger="quant_balance")

    with (
        patch("quant_balance.services.backtest_service.load_dataframe", return_value=sample_df),
        patch(
            "quant_balance.services.backtest_service.optimize",
            return_value=_fake_optimize_result(candidate_count=4),
        ),
    ):
        run_optimize(
            symbol="600519.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            strategy="sma_cross",
            maximize="Sharpe Ratio",
            param_ranges={"fast_period": [5, 6], "slow_period": [20, 30]},
        )

    records = [
        record for record in caplog.records
        if getattr(record, "qb_event", None) == "BACKTEST_OPTIMIZE"
    ]
    assert len(records) == 1
    payload = records[0].qb_payload
    assert payload["stage"] == "service"
    assert payload["strategy"] == "sma_cross"
    assert payload["symbol"] == "600519.SH"
    assert payload["candidate_count"] == 4
