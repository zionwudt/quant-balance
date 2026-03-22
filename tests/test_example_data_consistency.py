from __future__ import annotations

from quant_balance.cli import DEFAULT_EXAMPLE_PATH, run_demo_backtest
from quant_balance.web_demo import run_demo_web_backtest



def test_web_example_mode_matches_cli_builtin_example_dataset() -> None:
    cli_report = run_demo_backtest(
        csv_path=DEFAULT_EXAMPLE_PATH,
        symbol="600519.SH",
        initial_cash=100_000.0,
        short_window=5,
        long_window=20,
    )
    web_result = run_demo_web_backtest(
        form_data={
            "input_mode": "example",
            "symbol": "600519.SH",
            "initial_cash": "100000",
            "short_window": "5",
            "long_window": "20",
        }
    )

    assert web_result.run_context is not None
    assert web_result.run_context["bars_count"] == 18
    assert web_result.run_context["date_range_end"] == "2026-01-28"
    assert web_result.summary["final_equity"] == cli_report.final_equity
    assert web_result.summary["trades_count"] == cli_report.trades_count
    assert web_result.summary["max_drawdown_end"] == cli_report.max_drawdown_end.isoformat()
