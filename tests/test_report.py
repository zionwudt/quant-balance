"""测试报告格式化工具。"""

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


def test_equity_curve_to_dicts():
    df = _make_sample_df()
    result = run_backtest(df, SmaCross, strategy_params={"fast_period": 5, "slow_period": 20})

    curve = equity_curve_to_dicts(result.equity_curve)
    assert isinstance(curve, list)
    assert len(curve) > 0
    assert "date" in curve[0]
    assert "equity" in curve[0]


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
