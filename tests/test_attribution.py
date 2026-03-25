"""测试组合归因模块。"""

from __future__ import annotations

import pytest
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


def test_portfolio_attribution_sums_match_returns_and_costs():
    data = {
        "AAA": _make_symbol_df(10.0, 0.20, days=40),
        "BBB": _make_symbol_df(20.0, -0.05, days=40),
    }

    result = run_portfolio_backtest(
        data,
        allocation="custom",
        custom_weights={"AAA": 0.75, "BBB": 0.25},
        rebalance_frequency="daily",
        cash=100_000.0,
        commission=0.001,
        symbol_metadata={
            "AAA": {"name": "成长股A", "industry": "科技"},
            "BBB": {"name": "防御股B", "industry": "银行"},
        },
    )

    attribution = result.attribution
    stock_contribution_sum = sum(item.contribution_pct for item in attribution.stock_contributions)
    brinson_effect_sum = sum(item.effect_pct for item in attribution.sector_allocation)
    brinson_effect_sum += sum(item.effect_pct for item in attribution.sector_selection)
    brinson_effect_sum += sum(item.effect_pct for item in attribution.sector_interaction)

    assert stock_contribution_sum == pytest.approx(result.report["total_return_pct"], abs=1e-4)
    assert brinson_effect_sum == pytest.approx(attribution.benchmark.excess_return_pct, abs=1e-4)
    assert attribution.cost_breakdown.total_cost == pytest.approx(attribution.cost_breakdown.commission)
    assert attribution.cost_breakdown.total_cost > 0
    assert {item.sector for item in attribution.stock_contributions} == {"科技", "银行"}
    assert len(attribution.sector_summary) == 2
