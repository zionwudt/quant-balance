from datetime import date

import pytest

from quant_balance.api.meta import (
    build_backtest_meta,
    get_backtest_field_guide,
)
from quant_balance.api.presenters import build_backtest_response
from quant_balance.services.backtest_inputs import BacktestInputError, BacktestRequest
from quant_balance.core.report import generate_report


def test_backtest_request_rejects_invalid_ma_parameters() -> None:
    with pytest.raises(BacktestInputError, match="短均线必须小于长均线"):
        BacktestRequest(
            symbol="600519.SH", start_date="2024-01-01", end_date="2024-06-30",
            short_window=20, long_window=10,
        ).validate()

    with pytest.raises(BacktestInputError, match="不要超过 250"):
        BacktestRequest(
            symbol="600519.SH", start_date="2024-01-01", end_date="2024-06-30",
            short_window=5, long_window=300,
        ).validate()


def test_backtest_request_rejects_bad_date_format() -> None:
    with pytest.raises(BacktestInputError, match="start_date 格式不正确"):
        BacktestRequest(
            symbol="600519.SH", start_date="20240101", end_date="2024-06-30",
        ).validate()


def test_backtest_request_rejects_start_after_end() -> None:
    with pytest.raises(BacktestInputError, match="start_date 不能晚于 end_date"):
        BacktestRequest(
            symbol="600519.SH", start_date="2024-06-30", end_date="2024-01-01",
        ).validate()


def test_backtest_request_rejects_empty_symbol() -> None:
    with pytest.raises(BacktestInputError, match="请填写股票代码"):
        BacktestRequest(
            symbol="  ", start_date="2024-01-01", end_date="2024-06-30",
        ).validate()


def test_field_guide_content() -> None:
    guide = get_backtest_field_guide()

    assert "Tushare" in guide.supported_frequency
    assert "印花税" in guide.notes[0]


def test_build_backtest_meta_structure() -> None:
    meta = build_backtest_meta()

    assert meta.server_mode == "api"
    assert "Tushare" in meta.field_guide.supported_frequency


def test_build_backtest_response_exposes_summary_trades_and_assumptions() -> None:
    report = generate_report(
        initial_equity=100_000.0,
        equity_curve=[100_000.0, 102_000.0, 101_000.0],
        equity_dates=[date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)],
        fills=[],
        benchmark_name="CSI300",
        benchmark_equity_curve=[100.0, 101.0, 100.5],
    )

    response = build_backtest_response(report)

    assert response.chart_sections == ["summary", "trades", "equity_curve", "run_context", "export"]
    assert response.summary["benchmark_name"] == "CSI300"
    assert response.summary["max_drawdown_start"] == "2026-01-06"
    assert response.summary["max_drawdown_end"] == "2026-01-07"
    assert response.closed_trades == []
    assert any("滑点" in note for note in response.assumptions)
    assert response.export_json is not None
    assert response.run_context == {}
    assert response.equity_curve_points == []
