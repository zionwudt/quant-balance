from __future__ import annotations

from pathlib import Path


def test_readme_web_demo_copy_matches_real_file_upload_flow() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")

    assert "upload a real local CSV file" in readme
    assert "textarea-based CSV path only as a developer/debug fallback" in readme
    assert 'the "upload CSV" flow is temporarily implemented as textarea paste input' not in readme
    assert "paste uploaded CSV content into the page" not in readme
