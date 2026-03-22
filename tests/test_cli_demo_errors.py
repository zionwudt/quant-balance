from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_demo_cli_returns_user_friendly_error_for_invalid_ma_combo() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "quant_balance.main", "demo", "--short-window", "20", "--long-window", "10"],
        cwd=root,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / 'src')},
    )

    assert result.returncode != 0
    assert "错误：短均线必须小于长均线。" in result.stderr
    assert "Traceback" not in result.stderr


def test_demo_cli_returns_user_friendly_error_for_missing_csv() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "quant_balance.main", "demo", "--csv", "/tmp/not-found.csv"],
        cwd=root,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / 'src')},
    )

    assert result.returncode != 0
    assert "错误：找不到 CSV 文件 /tmp/not-found.csv。" in result.stderr
    assert "Traceback" not in result.stderr


def test_demo_cli_returns_user_friendly_error_for_invalid_csv_content(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("date,open,high,low,close\n2026-01-05,10,11,9,10.5\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "quant_balance.main", "demo", "--csv", str(bad_csv)],
        cwd=root,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root / 'src')},
    )

    assert result.returncode != 0
    assert "错误：CSV 缺少必要字段：volume。请下载模板后按模板列名准备数据。" in result.stderr
    assert "Traceback" not in result.stderr
