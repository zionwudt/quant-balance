from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_cli_returns_user_friendly_error_for_missing_example_csv() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quant_balance.main",
            "--example-csv",
            "/tmp/no-such.csv",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / 'src')},
    )

    assert result.returncode != 0
    assert "错误：找不到示例 CSV 文件 /tmp/no-such.csv。请检查 --example-csv 参数。" in result.stderr
    assert "Traceback" not in result.stderr
