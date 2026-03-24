"""测试报告格式化工具。"""

import json
import math

import pandas as pd

from quant_balance.core.backtest import run_backtest
from quant_balance.core.report import bt_trades_to_dicts, equity_curve_to_dicts, normalize_bt_stats
from quant_balance.core.strategies import SmaCross


def _make_sample_df(days: int = 200) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    close = [10.0 + index * 0.1 for index in range(days)]
    return pd.DataFrame({
        "Open": [value - 0.05 for value in close],
        "High": [value + 0.1 for value in close],
        "Low": [value - 0.1 for value in close],
        "Close": close,
        "Volume": [1_000_000] * days,
    }, index=dates)


def test_bt_trades_to_dicts():
    df = _make_sample_df()
    result = run_backtest(df, SmaCross, strategy_params={"fast_period": 5, "slow_period": 20})

    trades = bt_trades_to_dicts(result.trades)
    assert isinstance(trades, list)
    if trades:
        assert "entry_price" in trades[0]
        assert "exit_price" in trades[0]
        assert "pnl" in trades[0]


def test_bt_trades_to_dicts_includes_risk_fields():
    trades_df = pd.DataFrame([
        {
            "Size": 100,
            "EntryBar": 0,
            "ExitBar": 1,
            "EntryPrice": 100.0,
            "ExitPrice": 94.0,
            "SL": 95.0,
            "TP": 120.0,
            "PnL": -600.0,
            "ReturnPct": -0.06,
            "EntryTime": "2024-01-01 00:00:00",
            "ExitTime": "2024-01-02 00:00:00",
            "Duration": "1 days 00:00:00",
        }
    ])

    trades = bt_trades_to_dicts(
        trades_df,
        risk_params={"stop_loss_pct": 0.05, "take_profit_pct": 0.2},
    )

    assert trades[0]["stop_loss_price"] == 95.0
    assert trades[0]["take_profit_price"] == 120.0
    assert trades[0]["exit_reason"] == "stop_loss"


def test_equity_curve_to_dicts():
    df = _make_sample_df()
    result = run_backtest(df, SmaCross, strategy_params={"fast_period": 5, "slow_period": 20})

    curve = equity_curve_to_dicts(result.equity_curve)
    assert isinstance(curve, list)
    assert len(curve) > 0
    assert "date" in curve[0]
    assert "equity" in curve[0]


def test_equity_curve_to_dicts_includes_benchmark_fields():
    equity_df = pd.DataFrame(
        {"Equity": [100_000.0, 102_000.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    benchmark_df = pd.DataFrame(
        {"Close": [10.0, 10.5]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )

    curve = equity_curve_to_dicts(equity_df, benchmark_df=benchmark_df)

    assert curve[0]["benchmark_equity"] == 100_000.0
    assert curve[1]["benchmark_equity"] == 105_000.0
    assert curve[1]["strategy_return_pct"] == 2.0
    assert curve[1]["benchmark_return_pct"] == 5.0
    assert curve[1]["excess_return_pct"] == -3.0
    json.dumps(curve, allow_nan=False)


def test_empty_trades_df():
    assert bt_trades_to_dicts(pd.DataFrame()) == []
    assert bt_trades_to_dicts(None) == []


def test_empty_equity_df():
    assert equity_curve_to_dicts(pd.DataFrame()) == []
    assert equity_curve_to_dicts(None) == []


def test_normalize_bt_stats_returns_stable_keys():
    report = normalize_bt_stats(pd.Series({"Return [%]": 10.5, "Sharpe Ratio": 1.2}))

    assert report["total_return_pct"] == 10.5
    assert report["sharpe_ratio"] == 1.2
    assert report["final_equity"] is None


def test_normalize_bt_stats_reads_initial_equity_from_equity_curve():
    report = normalize_bt_stats(pd.Series({
        "_equity_curve": pd.DataFrame({"Equity": [100_000.0, 101_000.0]}),
        "Max. Drawdown [%]": -12.5,
    }))

    assert report["initial_equity"] == 100_000.0
    assert report["max_drawdown_pct"] == 12.5


def test_normalize_bt_stats_includes_risk_summary():
    trades_df = pd.DataFrame([
        {
            "EntryPrice": 100.0,
            "ExitPrice": 94.0,
            "SL": 95.0,
            "TP": 120.0,
        }
    ])
    report = normalize_bt_stats(
        pd.Series({
            "_equity_curve": pd.DataFrame({"Equity": [100_000.0, 99_400.0]}),
            "_trades": trades_df,
        }),
        risk_params={"stop_loss_pct": 0.05, "take_profit_pct": 0.2},
    )

    assert report["stop_loss_pct"] == 0.05
    assert report["take_profit_pct"] == 0.2
    assert report["stop_loss_trades"] == 1
    assert report["take_profit_trades"] == 0


def test_normalize_bt_stats_includes_enhanced_sections_and_benchmark_summary():
    dates = pd.date_range("2024-01-02", periods=80, freq="B")
    equity_values = [
        100_000.0 * (1 + index * 0.002 + math.sin(index / 5) * 0.01)
        for index in range(len(dates))
    ]
    benchmark_close = [
        10.0 * (1 + index * 0.0015 + math.cos(index / 7) * 0.005)
        for index in range(len(dates))
    ]
    equity_curve = pd.DataFrame({"Equity": equity_values}, index=dates)
    benchmark_df = pd.DataFrame({"Close": benchmark_close}, index=dates)

    report = normalize_bt_stats(
        pd.Series({
            "_equity_curve": equity_curve,
            "Equity Final [$]": equity_values[-1],
            "Return [%]": (equity_values[-1] / equity_values[0] - 1) * 100,
            "Return (Ann.) [%]": 24.0,
            "Sharpe Ratio": 1.6,
            "Sortino Ratio": 2.1,
            "Max. Drawdown [%]": -4.0,
            "# Trades": 5,
        }),
        benchmark_df=benchmark_df,
        benchmark_symbol="000300.SH",
        rolling_sharpe_window=20,
    )

    assert report["calmar_ratio"] == 6.0
    assert report["rolling_sharpe_window_bars"] == 20
    assert len(report["monthly_returns"]) >= 3
    assert len(report["rolling_sharpe"]) > 0
    assert len(report["yearly_stats"]) == 1
    assert report["benchmark_symbol"] == "000300.SH"
    assert "benchmark_total_return_pct" in report
    assert "beta" in report
    assert "alpha_annualized_pct" in report
    json.dumps(report, allow_nan=False)
