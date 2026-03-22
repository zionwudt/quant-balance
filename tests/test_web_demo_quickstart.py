from __future__ import annotations

from io import BytesIO
from pathlib import Path

from quant_balance.web_demo import create_app, render_demo_page


def test_render_demo_page_exposes_one_click_example_cta() -> None:
    html = render_demo_page()

    assert 'data-testid="qb-use-example"' in html
    assert '用示例数据立即体验' in html
    assert 'name="quick_action"' in html
    assert 'value="example-run"' in html


def test_one_click_example_cta_runs_happy_path(tmp_path: Path) -> None:
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

    body = (
        "quick_action=example-run&input_mode=upload&symbol=600519.SH&initial_cash=100000&short_window=5&long_window=10"
    ).encode("utf-8")
    response = app(
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/demo",
            "wsgi.input": BytesIO(body),
            "CONTENT_LENGTH": str(len(body)),
        },
        start_response,
    )
    html = b"".join(response).decode("utf-8")

    assert captured["status"] == "200 OK"
    assert 'data-testid="qb-result-panel"' in html
    assert 'data-testid="qb-demo-success"' in html
