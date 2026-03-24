from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from quant_balance.data.tushare_loader import (
    _CREATE_ADJ_FACTOR_SQL,
    _CREATE_TABLE_SQL,
    load_bar_views,
    load_bars,
)


def _seed_cache(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(_CREATE_TABLE_SQL)
    conn.execute(_CREATE_ADJ_FACTOR_SQL)
    conn.executemany(
        "INSERT INTO daily_bars (ts_code, trade_date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("AAA", "20260105", 10.0, 10.0, 10.0, 10.0, 1_000.0),
            ("AAA", "20260106", 9.5, 9.5, 9.5, 9.5, 1_000.0),
        ],
    )
    conn.executemany(
        "INSERT INTO daily_adj_factors (ts_code, trade_date, adj_factor) VALUES (?, ?, ?)",
        [
            ("AAA", "20260105", 1.0),
            ("AAA", "20260106", 1.0526315789473684),
        ],
    )
    conn.commit()
    conn.close()


def test_load_bar_views_returns_raw_and_forward_adjusted_series(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    _seed_cache(db_path)

    bar_views = load_bar_views("AAA", "2026-01-05", "2026-01-06", db_path=db_path)

    assert [bar.close for bar in bar_views.trade_bars] == [10.0, 9.5]
    assert [bar.close for bar in bar_views.indicator_bars] == pytest.approx([9.5, 9.5])


def test_load_bars_keeps_backward_compatible_raw_prices(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    _seed_cache(db_path)

    bars = load_bars("AAA", "2026-01-05", "2026-01-06", db_path=db_path)

    assert [bar.close for bar in bars] == [10.0, 9.5]
