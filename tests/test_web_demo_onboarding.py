from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from quant_balance.web_demo import render_demo_page


def test_render_demo_page_shows_first_run_guide() -> None:
    html = render_demo_page()

    assert 'data-testid="first-run-guide"' in html
    assert "第一次使用建议" in html
    assert "三步完成" in html


def test_help_mentions_open_browser_flag() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "quant_balance.main", "--help"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / 'src')},
    )

    help_text = result.stdout

    assert "--open-browser" in help_text
    assert "启动后自动打开浏览器" in help_text
