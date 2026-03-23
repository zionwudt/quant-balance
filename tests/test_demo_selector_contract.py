from __future__ import annotations

from quant_balance.web_demo import render_demo_page


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


def test_rendered_page_exposes_documented_qb_selectors() -> None:
    html = render_demo_page(
        form_data={
            "input_mode": "example",
            "symbol": "600519.SH",
            "initial_cash": "100000",
            "short_window": "5",
            "long_window": "10",
        }
    )

    for testid in REQUIRED_CONTRACT_SELECTORS:
        assert f'data-testid="{testid}"' in html

    assert 'data-testid="qb-result-summary"' in html
    assert 'data-testid="qb-result-trades"' in html
    assert 'data-testid="qb-result-assumptions"' in html
