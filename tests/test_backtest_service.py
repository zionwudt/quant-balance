from __future__ import annotations

from pathlib import Path

from quant_balance.backtest_inputs import BacktestRequest
from quant_balance.services.backtest_service import run_moving_average_backtest


def test_run_moving_average_backtest_returns_context_and_equity_curve() -> None:
    result = run_moving_average_backtest(
        BacktestRequest(
            input_mode="example",
            symbol="600519.SH",
            initial_cash=100_000.0,
            short_window=2,
            long_window=3,
        )
    )

    assert result.report.final_equity > 0
    assert result.run_context["input_mode"] == "example"
    assert result.run_context["bars_count"] == 4
    assert len(result.equity_curve_points) == 4


def test_run_moving_average_backtest_prefers_example_csv_path_when_provided(tmp_path: Path) -> None:
    example_csv = tmp_path / "example.csv"
    example_csv.write_text(
        "date,open,high,low,close,volume\n"
        "2026-01-05,10.0,10.2,9.9,10.1,1000\n"
        "2026-01-06,10.1,10.3,10.0,10.2,1100\n"
        "2026-01-07,10.2,10.4,10.1,10.3,1200\n"
        "2026-01-08,10.3,10.5,10.2,10.4,1300\n"
        "2026-01-09,10.4,10.6,10.3,10.5,1400\n",
        encoding="utf-8",
    )

    result = run_moving_average_backtest(
        BacktestRequest(
            input_mode="example",
            symbol="600519.SH",
            initial_cash=100_000.0,
            short_window=2,
            long_window=3,
        ),
        example_csv_path=example_csv,
    )

    assert result.run_context["bars_count"] == 5
    assert result.run_context["date_range_start"] == "2026-01-05"
    assert result.run_context["date_range_end"] == "2026-01-09"
