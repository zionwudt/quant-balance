from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_OUTPUT = "QuantBalance is ready.\nUse 'quant-balance --help' to explore commands, or try 'quant-balance demo' and 'quant-balance web-demo'."


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

    result = subprocess.run(
        [str(cli_bin)],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == EXPECTED_OUTPUT


def test_module_entrypoint_runs_after_install(tmp_path: Path) -> None:
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
        [str(python_bin), "-m", "quant_balance.main"],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == EXPECTED_OUTPUT
