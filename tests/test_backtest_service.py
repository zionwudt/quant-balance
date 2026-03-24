from __future__ import annotations

from datetime import date
from unittest.mock import patch

from quant_balance.data.tushare_loader import LoadedBarViews
from quant_balance.services.backtest_inputs import BacktestRequest
from quant_balance.core.models import MarketBar
from quant_balance.services.backtest_service import run_moving_average_backtest

MOCK_BARS = [
    MarketBar(symbol="600519.SH", date=date(2024, 1, 2), open=10.0, high=10.2, low=9.9, close=10.1, volume=1000),
    MarketBar(symbol="600519.SH", date=date(2024, 1, 3), open=10.1, high=10.3, low=10.0, close=10.2, volume=1100),
    MarketBar(symbol="600519.SH", date=date(2024, 1, 4), open=10.2, high=10.4, low=10.1, close=10.3, volume=1200),
    MarketBar(symbol="600519.SH", date=date(2024, 1, 5), open=10.3, high=10.5, low=10.2, close=10.4, volume=1300),
]


@patch(
    "quant_balance.services.backtest_service.load_bar_views",
    return_value=LoadedBarViews(trade_bars=MOCK_BARS, indicator_bars=MOCK_BARS),
)
def test_run_moving_average_backtest_returns_context_and_equity_curve(mock_load: object) -> None:
    result = run_moving_average_backtest(
        BacktestRequest(
            symbol="600519.SH",
            start_date="2024-01-02",
            end_date="2024-01-05",
            initial_cash=100_000.0,
            short_window=2,
            long_window=3,
        )
    )

    assert result.report.final_equity > 0
    assert result.run_context["symbol"] == "600519.SH"
    assert result.run_context["bars_count"] == 4
    assert len(result.equity_curve_points) == 4
