from __future__ import annotations

from pathlib import Path


def test_readme_web_demo_copy_matches_chinese_content() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")

    assert "知衡" in readme
    assert "A股" in readme
    assert "quant-balance --open-browser" in readme
    assert "CSV" in readme
