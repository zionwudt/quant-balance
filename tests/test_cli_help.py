from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_demo_help_does_not_expose_redundant_action_layer() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "quant_balance.main", "demo", "--help"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / 'src')},
    )

    help_text = result.stdout

    assert "{run}" not in help_text
    assert "demo action to execute" not in help_text
    assert "--csv" in help_text
    assert "--symbol" in help_text
    assert "--initial-cash" in help_text
