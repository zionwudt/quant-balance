from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_python_dash_m_quant_balance_demo_prints_migration_hint() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "quant_balance.demo", "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / 'src')},
    )

    assert result.returncode != 0
    assert "请改用：python -m quant_balance demo --help" in result.stderr
    assert "quant-balance demo --help" in result.stderr


def test_python_dash_m_quant_balance_web_demo_prints_migration_hint() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "quant_balance.web_demo", "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / 'src')},
    )

    assert result.returncode != 0
    assert "请改用：python -m quant_balance web-demo --help" in result.stderr
    assert "quant-balance web-demo --help" in result.stderr
