from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from quant_balance.cli import ROOT_COMMAND_HINT


def test_root_command_prints_discoverable_next_steps() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "quant_balance.main"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / 'src')},
    )

    lines = result.stdout.strip().splitlines()

    assert lines[0] == "QuantBalance is ready."
    assert ROOT_COMMAND_HINT in result.stdout
    assert "--help" in result.stdout
    assert "demo" in result.stdout
    assert "web-demo" in result.stdout
