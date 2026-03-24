from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest

from quant_balance.data.cb_loader import (
    _CREATE_CB_BASIC_SQL,
    _CREATE_CB_DAILY_SQL,
    load_dataframe,
)
from quant_balance.data.tushare_loader import _CREATE_ADJ_FACTOR_SQL, _CREATE_TABLE_SQL


def _seed_cache(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(_CREATE_CB_DAILY_SQL)
    conn.execute(_CREATE_CB_BASIC_SQL)
    conn.execute(_CREATE_TABLE_SQL)
    conn.execute(_CREATE_ADJ_FACTOR_SQL)
    conn.executemany(
        "INSERT INTO cb_daily_bars "
        "(ts_code, trade_date, open, high, low, close, volume, amount, bond_value, bond_over_rate, cb_value, cb_over_rate) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("110043.SH", "20260105", 120.0, 121.0, 119.0, 120.5, 10_000.0, 5_000.0, 95.0, 26.84, 89.5, 34.64),
            ("110043.SH", "20260106", 121.0, 122.0, 120.0, 121.5, 11_000.0, 5_100.0, 95.2, 27.63, 90.0, 35.0),
        ],
    )
    conn.execute(
        "INSERT INTO cb_basic_info (ts_code, bond_short_name, stk_code, stk_short_name) VALUES (?, ?, ?, ?)",
        ("110043.SH", "转债测试", "600000.SH", "正股测试"),
    )
    conn.executemany(
        "INSERT INTO daily_bars (ts_code, trade_date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("600000.SH", "20260105", 8.90, 9.10, 8.80, 9.00, 100_000.0),
            ("600000.SH", "20260106", 8.95, 9.15, 8.85, 9.10, 110_000.0),
        ],
    )
    conn.commit()
    conn.close()


def test_load_dataframe_returns_cb_dataframe_with_research_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    _seed_cache(db_path)

    df = load_dataframe("110043.SH", "2026-01-05", "2026-01-06", db_path=db_path)

    assert list(df.columns) == [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "Amount",
        "BondValue",
        "PureBondPremiumRate",
        "ConversionValue",
        "ConversionPremiumRate",
        "UnderlyingClose",
        "ConversionPrice",
    ]
    assert list(df["UnderlyingClose"]) == [9.0, 9.1]
    assert df["ConversionPrice"].iloc[0] == pytest.approx(9.0 * 100 / 89.5)
    assert df.attrs["asset_type"] == "convertible_bond"
    assert df.attrs["underlying_symbol"] == "600000.SH"


def test_load_dataframe_emits_cache_hit_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    db_path = tmp_path / "cache.db"
    _seed_cache(db_path)
    caplog.set_level(logging.INFO, logger="quant_balance")

    load_dataframe("110043.SH", "2026-01-05", "2026-01-06", db_path=db_path)

    cache_records = [
        record for record in caplog.records
        if getattr(record, "qb_event", None) == "CACHE_HIT"
    ]
    payloads = [record.qb_payload for record in cache_records]
    assert any(payload["dataset"] == "cb_daily_bars" for payload in payloads)
    assert any(payload["dataset"] == "cb_basic_info" for payload in payloads)
