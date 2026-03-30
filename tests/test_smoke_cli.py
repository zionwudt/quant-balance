from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def _load_pyproject() -> dict:
    with open(ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def test_pyproject_declares_console_entrypoint() -> None:
    pyproject = _load_pyproject()

    assert pyproject["project"]["scripts"]["quant-balance"] == "quant_balance.main:main"


def test_pyproject_uses_src_layout() -> None:
    pyproject = _load_pyproject()

    assert pyproject["tool"]["setuptools"]["package-dir"] == {"": "src/backend"}
    assert pyproject["tool"]["setuptools"]["packages"]["find"]["where"] == ["src/backend"]
