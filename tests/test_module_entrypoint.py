from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_python_dash_m_quant_balance_help_works() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "quant_balance", "--help"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / 'src')},
    )

    help_text = result.stdout

    assert "--host" in help_text
    assert "--port" in help_text
    assert "知衡" in help_text or "QuantBalance" in help_text
