from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from quant_balance.report import SHORT_SAMPLE_WARNING, generate_report


def test_generate_report_degrades_annualized_metrics_for_short_samples() -> None:
    report = generate_report(
        initial_equity=100.0,
        equity_curve=[100.0, 101.0, 99.5, 100.5],
        equity_dates=[date(2026, 1, 1) + timedelta(days=i) for i in range(4)],
        fills=[],
    )

    assert report.sample_size_warning == SHORT_SAMPLE_WARNING
    assert report.annualized_return_pct is None
    assert report.annualized_volatility_pct is None
    assert report.sharpe_ratio is None
    assert report.sortino_ratio is None


def test_demo_json_output_marks_short_sample_metrics_as_null_and_warns() -> None:
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

    assert payload["sample_size_warning"] == SHORT_SAMPLE_WARNING
    assert payload["annualized_return_pct"] is None
    assert payload["annualized_volatility_pct"] is None
    assert payload["sharpe_ratio"] is None
    assert payload["sortino_ratio"] is None


def test_demo_text_summary_shows_short_sample_note() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "quant_balance.main", "demo"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / 'src')},
    )

    assert SHORT_SAMPLE_WARNING in result.stdout
