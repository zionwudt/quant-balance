"""测试组合回测服务层编排。"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from quant_balance.core.portfolio import PortfolioBacktestResult
from quant_balance.services.portfolio_service import run_portfolio_research


def _make_sample_df(days: int = 10, base_price: float = 10.0) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    close = [base_price + index * 0.1 for index in range(days)]
    return pd.DataFrame({
        "Open": close,
        "High": close,
        "Low": close,
        "Close": close,
        "Volume": [1_000_000] * days,
    }, index=dates)


def _fake_portfolio_result() -> PortfolioBacktestResult:
    index = pd.to_datetime(["2024-01-01", "2024-01-02"])
    return PortfolioBacktestResult(
        stats=pd.Series({"Total Return [%]": 5.0}),
        equity_curve=pd.Series([100_000.0, 105_000.0], index=index),
        weights=pd.DataFrame(
            {"AAA": [0.5, 0.5], "BBB": [0.5, 0.5]},
            index=index,
        ),
        rebalances=pd.DataFrame(
            {"turnover_pct": [100.0], "AAA": [0.5], "BBB": [0.5]},
            index=pd.to_datetime(["2024-01-01"]),
        ),
        report={"final_equity": 105_000.0, "rebalance_count": 1},
        close_matrix=pd.DataFrame(
            {"AAA": [10.0, 10.5], "BBB": [20.0, 19.5]},
            index=index,
        ),
    )


def test_run_portfolio_research_requires_symbols():
    with pytest.raises(ValueError, match="symbols 不能为空"):
        run_portfolio_research(
            symbols=[],
            start_date="2024-01-01",
            end_date="2024-06-30",
        )


def test_run_portfolio_research_returns_api_ready_payload():
    sample_data = {
        "AAA": _make_sample_df(base_price=10.0),
        "BBB": _make_sample_df(base_price=20.0),
    }
    with (
        patch("quant_balance.services.portfolio_service.load_multi_dataframes", return_value=sample_data) as mock_load,
        patch("quant_balance.services.portfolio_service.run_portfolio_backtest", return_value=_fake_portfolio_result()) as mock_run,
    ):
        result = run_portfolio_research(
            symbols=["AAA", "BBB"],
            start_date="2024-01-01",
            end_date="2024-06-30",
            allocation="equal",
            rebalance_frequency="monthly",
        )

    assert result["summary"]["final_equity"] == 105_000.0
    assert result["summary"]["rebalance_count"] == 1
    assert result["equity_curve"][0]["equity"] == 100_000.0
    assert result["weights"][0]["weights"]["AAA"] == 0.5
    assert result["rebalances"][0]["turnover_pct"] == 100.0
    assert result["run_context"]["loaded_symbols"] == ["AAA", "BBB"]
    mock_load.assert_called_once()
    mock_run.assert_called_once()


def test_run_portfolio_research_passes_data_provider():
    sample_data = {"AAA": _make_sample_df(base_price=10.0)}
    with (
        patch("quant_balance.services.portfolio_service.load_multi_dataframes", return_value=sample_data) as mock_load,
        patch("quant_balance.services.portfolio_service.run_portfolio_backtest", return_value=_fake_portfolio_result()),
    ):
        run_portfolio_research(
            symbols=["AAA"],
            start_date="2024-01-01",
            end_date="2024-06-30",
            data_provider="akshare",
        )

    mock_load.assert_called_once_with(
        ["AAA"],
        "2024-01-01",
        "2024-06-30",
        data_provider="akshare",
    )
