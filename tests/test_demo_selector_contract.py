from __future__ import annotations

from io import BytesIO
from pathlib import Path

from quant_balance.demo import get_demo_stable_selectors
from quant_balance.web_demo import create_app, render_demo_page


REQUIRED_CONTRACT_SELECTORS = [
    "qb-demo-page",
    "qb-input-mode",
    "qb-upload-input",
    "qb-symbol-input",
    "qb-initial-cash-input",
    "qb-short-window-input",
    "qb-long-window-input",
    "qb-submit-backtest",
]


def _render_success_html() -> str:
    return render_demo_page(
        form_data={
            "input_mode": "example",
            "symbol": "600519.SH",
            "initial_cash": "100000",
            "short_window": "5",
            "long_window": "10",
        }
    )


def test_rendered_page_exposes_documented_qb_selectors() -> None:
    html = render_demo_page()

    for testid in REQUIRED_CONTRACT_SELECTORS:
        assert f'data-testid="{testid}"' in html



def test_selector_contract_markers_exist_on_success_result_page() -> None:
    html = _render_success_html()

    assert 'data-testid="qb-result-summary"' in html
    assert 'data-testid="qb-result-trades"' in html
    assert 'data-testid="qb-result-assumptions"' in html



def test_selector_contract_markers_exist_on_validation_error_page() -> None:
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



def test_selector_contract_definition_and_rendered_page_stay_in_sync() -> None:
    html = _render_success_html()

    for selector in get_demo_stable_selectors():
        marker = selector.selector.replace("[data-testid='", 'data-testid="').replace("']", '"')
        assert marker in html, f"missing selector contract marker: {selector.selector}"



def test_selector_contract_definition_and_wsgi_response_stay_in_sync(tmp_path: Path) -> None:
    example_csv = tmp_path / "example.csv"
    example_csv.write_text(
        "date,open,high,low,close,volume\n"
        "2026-01-05,10,10.1,9.9,10,100000\n"
        "2026-01-06,10,10.2,9.9,10.1,100000\n"
        "2026-01-07,10.1,10.4,10.0,10.3,100000\n"
        "2026-01-08,10.2,10.5,10.1,10.4,100000\n",
        encoding="utf-8",
    )
    app = create_app(example_csv_path=example_csv)

    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    body = b"input_mode=example&symbol=600519.SH&initial_cash=100000&short_window=5&long_window=10"
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
    for selector in get_demo_stable_selectors():
        marker = selector.selector.replace("[data-testid='", 'data-testid="').replace("']", '"')
        assert marker in html, f"missing selector contract marker: {selector.selector}"
