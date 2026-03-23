from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_root_command_help_shows_web_server_options() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "quant_balance.main", "--help"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / 'src')},
    )

    assert "知衡" in result.stdout or "QuantBalance" in result.stdout
    assert "--host" in result.stdout
    assert "--port" in result.stdout
    assert "--open-browser" in result.stdout
