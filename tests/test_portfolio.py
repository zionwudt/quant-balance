"""测试 vectorbt 组合回测引擎。"""

from __future__ import annotations

import pandas as pd

from quant_balance.core.portfolio import run_portfolio_backtest


def _make_symbol_df(base_price: float, slope: float, days: int = 50) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    close = [base_price + index * slope for index in range(days)]
    return pd.DataFrame({
        "Open": close,
        "High": close,
        "Low": close,
        "Close": close,
        "Volume": [1_000_000] * days,
    }, index=dates)


def test_run_portfolio_backtest_equal_weight_monthly():
    data = {
        "AAA": _make_symbol_df(10.0, 0.2),
        "BBB": _make_symbol_df(20.0, -0.05),
    }

    result = run_portfolio_backtest(
        data,
        allocation="equal",
        rebalance_frequency="monthly",
        cash=100_000.0,
        commission=0.0,
    )

    assert result.report["symbols_count"] == 2
    assert result.report["rebalance_frequency"] == "monthly"
    assert result.report["initial_equity"] == 100_000.0
    assert not result.equity_curve.empty
    assert len(result.rebalances) >= 2
    assert len(result.report["monthly_returns"]) >= 2
    assert len(result.report["yearly_stats"]) == 1
    assert isinstance(result.report["rolling_sharpe"], list)
    assert result.weights.iloc[0]["AAA"] == 0.5
    assert result.weights.iloc[0]["BBB"] == 0.5


def test_run_portfolio_backtest_custom_weights_normalizes_input():
    data = {
        "AAA": _make_symbol_df(10.0, 0.2, days=10),
        "BBB": _make_symbol_df(20.0, 0.1, days=10),
    }

    result = run_portfolio_backtest(
        data,
        allocation="custom",
        custom_weights={"AAA": 3, "BBB": 1},
        rebalance_frequency="daily",
        cash=100_000.0,
        commission=0.0,
    )

    assert result.weights.iloc[0]["AAA"] == 0.75
    assert result.weights.iloc[0]["BBB"] == 0.25
    assert result.report["allocation"] == "custom"
    assert result.report["final_equity"] == result.report["final_value"]
