from __future__ import annotations

from io import BytesIO
from pathlib import Path

from quant_balance.report import SHORT_SAMPLE_WARNING
from quant_balance.web_demo import create_app, render_demo_page, run_demo_web_backtest


def test_render_demo_page_exposes_real_file_upload_entry() -> None:
    html = render_demo_page()

    assert 'enctype="multipart/form-data"' in html
    assert 'data-testid="csv-file-input"' in html
    assert 'data-testid="csv-upload-input"' in html
    assert 'data-testid="csv-upload-hint"' in html


def test_run_demo_web_backtest_prefers_uploaded_file_content_for_upload_mode() -> None:
    result = run_demo_web_backtest(
        form_data={
            "input_mode": "upload",
            "symbol": "600519.SH",
            "initial_cash": "100000",
            "short_window": "5",
            "long_window": "10",
            "csv_file_content": (
                "date,open,high,low,close,volume\n"
                "2026-01-05,10,10.1,9.9,10,100000\n"
                "2026-01-06,10.0,10.2,9.9,10.1,100000\n"
                "2026-01-07,10.1,10.4,10.0,10.3,100000\n"
                "2026-01-08,10.2,10.5,10.1,10.4,100000\n"
                "2026-01-09,10.3,10.6,10.2,10.5,100000\n"
                "2026-01-12,10.4,10.7,10.3,10.6,100000\n"
                "2026-01-13,10.5,10.8,10.4,10.7,100000\n"
                "2026-01-14,10.6,10.9,10.5,10.8,100000\n"
                "2026-01-15,10.7,11.0,10.6,10.9,100000\n"
                "2026-01-16,10.8,11.1,10.7,11.0,100000\n"
            ),
            "csv_filename": "bars.csv",
        }
    )

    assert result.summary["final_equity"] > 0
    assert result.sample_size_warning == SHORT_SAMPLE_WARNING


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

    assert 'data-testid="demo-error"' in html
    assert "短均线必须小于长均线" in html


def test_render_demo_page_shows_short_sample_warning_when_metrics_are_degraded() -> None:
    html = render_demo_page(
        form_data={
            "input_mode": "example",
            "symbol": "600519.SH",
            "initial_cash": "100000",
            "short_window": "5",
            "long_window": "10",
        }
    )

    assert 'data-testid="sample-size-warning"' in html
    assert SHORT_SAMPLE_WARNING in html


def test_create_app_handles_health_and_multipart_file_upload_flow(tmp_path: Path) -> None:
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

    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    multipart_body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="input_mode"\r\n\r\n'
        'upload\r\n'
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="symbol"\r\n\r\n'
        '600519.SH\r\n'
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="initial_cash"\r\n\r\n'
        '100000\r\n'
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="short_window"\r\n\r\n'
        '5\r\n'
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="long_window"\r\n\r\n'
        '10\r\n'
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="csv_file"; filename="bars.csv"\r\n'
        'Content-Type: text/csv\r\n\r\n'
        'date,open,high,low,close,volume\n'
        '2026-01-05,10,10.1,9.9,10,100000\n'
        '2026-01-06,10.0,10.2,9.9,10.1,100000\n'
        '2026-01-07,10.1,10.4,10.0,10.3,100000\n'
        '2026-01-08,10.2,10.5,10.1,10.4,100000\n'
        '2026-01-09,10.3,10.6,10.2,10.5,100000\n'
        '2026-01-12,10.4,10.7,10.3,10.6,100000\n'
        '2026-01-13,10.5,10.8,10.4,10.7,100000\n'
        '2026-01-14,10.6,10.9,10.5,10.8,100000\n'
        '2026-01-15,10.7,11.0,10.6,10.9,100000\n'
        '2026-01-16,10.8,11.1,10.7,11.0,100000\r\n'
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    page_response = app(
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/demo",
            "CONTENT_TYPE": f"multipart/form-data; boundary={boundary}",
            "wsgi.input": BytesIO(multipart_body),
            "CONTENT_LENGTH": str(len(multipart_body)),
        },
        start_response,
    )
    html = b"".join(page_response).decode("utf-8")

    assert captured["status"] == "200 OK"
    assert 'data-testid="demo-result"' in html
    assert 'data-testid="summary-table"' in html
    assert 'data-testid="trades-table"' in html
    assert '已选择文件：bars.csv' in html
