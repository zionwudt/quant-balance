from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path
def test_python_dash_m_quant_balance_can_be_imported() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-c", "from quant_balance.__main__ import main; print('ok')"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / 'src' / 'backend')},
    )
    assert "ok" in result.stdout
