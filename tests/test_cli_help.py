from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_help_shows_web_server_options() -> None:
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

    assert "--host" in help_text
    assert "--port" in help_text
    assert "--developer-mode" in help_text
    assert "--open-browser" in help_text
    assert "--example-csv" in help_text
    assert "--server-mode" not in help_text
