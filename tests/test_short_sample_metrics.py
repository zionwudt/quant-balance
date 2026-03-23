from __future__ import annotations

from datetime import date, timedelta

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
