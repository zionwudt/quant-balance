from __future__ import annotations

from io import BytesIO
from pathlib import Path

from quant_balance.web_demo import create_app, render_demo_page


def test_render_demo_page_exposes_real_file_upload_form() -> None:
    html = render_demo_page()

    assert 'enctype="multipart/form-data"' in html
    assert 'data-testid="qb-upload-input"' in html
    assert 'data-testid="csv-upload-hint"' in html
    assert 'data-testid="csv-upload-textarea"' in html



def test_wsgi_multipart_upload_flow_works_without_cgi_dependency(tmp_path: Path) -> None:
    example_csv = tmp_path / "example.csv"
    example_csv.write_text(
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
        "2026-01-16,10.8,11.1,10.7,11.0,100000\n",
        encoding="utf-8",
    )
    app = create_app(example_csv_path=example_csv)

    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

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

    response = app(
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/demo",
            "CONTENT_TYPE": f"multipart/form-data; boundary={boundary}",
            "wsgi.input": BytesIO(multipart_body),
            "CONTENT_LENGTH": str(len(multipart_body)),
        },
        start_response,
    )
    html = b"".join(response).decode("utf-8")

    assert captured["status"] == "200 OK"
    assert 'data-testid="qb-result-panel"' in html
    assert '已选择文件：bars.csv' in html
