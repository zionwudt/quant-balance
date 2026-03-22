from __future__ import annotations

from pathlib import Path


REQUIRED_IGNORE_RULES = [
    "*.egg-info/",
    ".eggs/",
    "build/",
    "dist/",
]


def test_gitignore_covers_python_build_outputs() -> None:
    root = Path(__file__).resolve().parents[1]
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")

    for rule in REQUIRED_IGNORE_RULES:
        assert rule in gitignore
