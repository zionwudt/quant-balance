from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_package_install_exposes_console_entrypoint(tmp_path: Path) -> None:
    venv_dir = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, cwd=ROOT)

    if sys.platform == "win32":
        python_bin = venv_dir / "Scripts" / "python.exe"
        cli_bin = venv_dir / "Scripts" / "quant-balance.exe"
    else:
        python_bin = venv_dir / "bin" / "python"
        cli_bin = venv_dir / "bin" / "quant-balance"

    subprocess.run(
        [str(python_bin), "-m", "pip", "install", "-e", str(ROOT)],
        check=True,
        cwd=ROOT,
    )

    assert cli_bin.exists(), f"console entrypoint {cli_bin} not found after install"


def test_module_entrypoint_importable_after_install(tmp_path: Path) -> None:
    venv_dir = tmp_path / "venv-module"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, cwd=ROOT)

    if sys.platform == "win32":
        python_bin = venv_dir / "Scripts" / "python.exe"
    else:
        python_bin = venv_dir / "bin" / "python"

    subprocess.run(
        [str(python_bin), "-m", "pip", "install", "-e", str(ROOT)],
        check=True,
        cwd=ROOT,
    )

    result = subprocess.run(
        [str(python_bin), "-c", "from quant_balance.main import run_cli; print('ok')"],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert "ok" in result.stdout
