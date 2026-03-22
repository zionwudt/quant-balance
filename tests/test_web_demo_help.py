from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_web_demo_help_does_not_expose_redundant_action_layer() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "quant_balance.main", "web-demo", "--help"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / 'src')},
    )

    help_text = result.stdout

    assert "{serve}" not in help_text
    assert "web demo action to execute" not in help_text
    assert "--host" in help_text
    assert "--port" in help_text
    assert "--developer-mode" in help_text
