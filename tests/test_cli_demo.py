from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from quant_balance.cli import DEFAULT_EXAMPLE_PATH, format_demo_summary, run_demo_backtest


def test_run_demo_backtest_returns_report_from_builtin_example() -> None:
    report = run_demo_backtest(
        csv_path=DEFAULT_EXAMPLE_PATH,
        symbol="600519.SH",
        initial_cash=100_000.0,
        short_window=5,
        long_window=10,
    )

    assert report.final_equity > 0
    assert report.trades_count >= 1
    assert report.max_drawdown_pct >= 0


def test_format_demo_summary_contains_quickstart_metrics() -> None:
    report = run_demo_backtest(
        csv_path=DEFAULT_EXAMPLE_PATH,
        symbol="600519.SH",
        initial_cash=100_000.0,
        short_window=5,
        long_window=10,
    )

    summary = format_demo_summary(report, csv_path=DEFAULT_EXAMPLE_PATH, symbol="600519.SH", short_window=5, long_window=10)

    assert "QuantBalance Demo Backtest" in summary
    assert "Strategy: MA cross (5/10)" in summary
    assert "Total return:" in summary
    assert "Max drawdown:" in summary


def test_module_demo_command_supports_json_output() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "quant_balance.main", "demo", "--json"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / 'src')},
    )

    payload = json.loads(result.stdout)

    assert payload["final_equity"] > 0
    assert payload["trades_count"] >= 1
    assert payload["max_drawdown_start"] is not None
    assert payload["sample_size_warning"] is not None
