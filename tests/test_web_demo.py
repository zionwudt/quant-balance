from __future__ import annotations

from io import BytesIO
from pathlib import Path

from quant_balance.report import SHORT_SAMPLE_WARNING
from quant_balance.web_demo import create_app, render_demo_page, run_demo_web_backtest


def test_render_demo_page_exposes_form_result_anchors_and_example_preview() -> None:
    html = render_demo_page()

    assert 'data-testid="qb-demo-page"' in html
    assert 'data-testid="qb-demo-form"' in html
    assert 'data-testid="qb-input-mode"' in html
    assert 'data-testid="qb-upload-input"' in html


def test_run_demo_web_backtest_returns_summary_trades_assumptions_and_run_context() -> None:
    result = run_demo_web_backtest(
        form_data={
            "input_mode": "example",
            "symbol": "600519.SH",
            "initial_cash": "100000",
            "short_window": "5",
            "long_window": "10",
        }
    )

    assert result.summary["final_equity"] > 0
    assert "summary" in result.chart_sections
    assert any("印花税" in note for note in result.assumptions)
    assert result.sample_size_warning == SHORT_SAMPLE_WARNING
    assert result.run_context is not None
    assert result.run_context["input_mode"] == "example"
    assert result.run_context["bars_count"] == 18
    assert result.run_context["date_range_end"] == "2026-01-28"
    assert result.export_json is not None
    assert result.equity_curve_points is not None


def test_render_demo_page_shows_friendly_validation_error_for_invalid_ma_combo() -> None:
    html = render_demo_page(
        form_data={
            "input_mode": "example",
            "symbol": "600519.SH",
            "initial_cash": "100000",
            "short_window": "20",
            "long_window": "10",
        }
    )

    assert 'data-testid="qb-demo-error"' in html
    assert "短均线必须小于长均线" in html


def test_render_demo_page_shows_short_sample_warning_context_export_and_equity_curve() -> None:
    html = render_demo_page(
        form_data={
            "input_mode": "example",
            "symbol": "600519.SH",
            "initial_cash": "100000",
            "short_window": "5",
            "long_window": "10",
        }
    )

    assert 'data-testid="qb-sample-size-warning"' in html
    assert 'data-testid="qb-run-context"' in html
    assert 'data-testid="qb-export-json"' in html
    assert 'data-testid="qb-equity-curve"' in html
    assert SHORT_SAMPLE_WARNING in html


def test_create_app_handles_health_and_demo_post_flow(tmp_path: Path) -> None:
    example_csv = tmp_path / "example.csv"
    example_csv.write_text(
        "date,open,high,low,close,volume\n"
        "2026-01-05,10,10.1,9.9,10,100000\n"
        "2026-01-06,9.9,10.2,9.8,10.1,110000\n"
        "2026-01-07,10.0,10.4,9.9,10.3,120000\n"
        "2026-01-08,10.2,10.6,10.1,10.5,130000\n"
        "2026-01-09,10.4,10.8,10.2,10.7,140000\n"
        "2026-01-12,10.6,11.0,10.5,10.9,150000\n"
        "2026-01-13,10.8,11.2,10.7,11.1,160000\n"
        "2026-01-14,11.0,11.4,10.9,11.3,170000\n"
        "2026-01-15,11.2,11.6,11.1,11.5,180000\n"
        "2026-01-16,11.4,11.8,11.3,11.7,190000\n",
        encoding="utf-8",
    )
    app = create_app(example_csv_path=example_csv)

    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    health_response = app(
        {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/health",
            "wsgi.input": BytesIO(b""),
            "CONTENT_LENGTH": "0",
        },
        start_response,
    )
    assert captured["status"] == "200 OK"
    assert b"ok" == b"".join(health_response)

    body = (
        "input_mode=example&symbol=600519.SH&initial_cash=100000&short_window=5&long_window=10"
    ).encode("utf-8")
    page_response = app(
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/demo",
            "wsgi.input": BytesIO(body),
            "CONTENT_LENGTH": str(len(body)),
        },
        start_response,
    )
    html = b"".join(page_response).decode("utf-8")

    assert captured["status"] == "200 OK"
    assert 'data-testid="qb-result-panel"' in html
    assert 'data-testid="qb-result-summary"' in html
    assert 'data-testid="qb-result-trades"' in html
    assert 'data-testid="qb-result-assumptions"' in html
    assert 'data-testid="qb-run-context"' in html
    assert 'data-testid="qb-export-json"' in html
    assert 'data-testid="qb-equity-curve"' in html
