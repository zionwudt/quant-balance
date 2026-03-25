from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from quant_balance.data.tushare_loader import (
    _CREATE_ADJ_FACTOR_SQL,
    _CREATE_MINUTE_TABLE_SQL,
    _CREATE_TABLE_SQL,
    _fetch_from_tushare,
    _fetch_minute_from_tushare,
    load_dataframe,
)


def _seed_cache(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(_CREATE_TABLE_SQL)
    conn.execute(_CREATE_ADJ_FACTOR_SQL)
    conn.execute(_CREATE_MINUTE_TABLE_SQL)
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


def _seed_minute_cache(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(_CREATE_MINUTE_TABLE_SQL)
    conn.executemany(
        "INSERT INTO minute_bars (ts_code, trade_time, timeframe, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("AAA", "2026-01-05 09:30:00", "1min", 10.0, 10.1, 9.9, 10.05, 500.0),
            ("AAA", "2026-01-05 09:31:00", "1min", 10.05, 10.2, 10.0, 10.15, 650.0),
        ],
    )
    conn.commit()
    conn.close()


def test_load_dataframe_returns_forward_adjusted_prices(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    _seed_cache(db_path)

    df = load_dataframe("AAA", "2026-01-05", "2026-01-06", db_path=db_path)

    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df.index[0].strftime("%Y-%m-%d") == "2026-01-05"
    assert list(df["Close"]) == pytest.approx([9.5, 9.5])


def test_load_dataframe_can_return_raw_prices(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    _seed_cache(db_path)

    df = load_dataframe("AAA", "2026-01-05", "2026-01-06", adjust="none", db_path=db_path)

    assert list(df["Close"]) == [10.0, 9.5]


def test_load_dataframe_emits_cache_hit_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    db_path = tmp_path / "cache.db"
    _seed_cache(db_path)
    caplog.set_level(logging.INFO, logger="quant_balance")

    load_dataframe("AAA", "2026-01-05", "2026-01-06", db_path=db_path)

    cache_records = [
        record for record in caplog.records
        if getattr(record, "qb_event", None) == "CACHE_HIT"
    ]
    payloads = [record.qb_payload for record in cache_records]

    assert any(payload["dataset"] == "daily_bars" for payload in payloads)
    assert any(payload["dataset"] == "daily_adj_factors" for payload in payloads)


def test_load_dataframe_can_return_minute_bars_from_cache(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    _seed_minute_cache(db_path)

    df = load_dataframe(
        "AAA",
        "2026-01-05 09:30:00",
        "2026-01-05 09:31:00",
        timeframe="1min",
        db_path=db_path,
    )

    assert list(df["Close"]) == [10.05, 10.15]
    assert df.index[0].strftime("%Y-%m-%d %H:%M:%S") == "2026-01-05 09:30:00"
    assert df.attrs["timeframe"] == "1min"
    assert df.attrs["price_adjustment"] == "none"


def test_fetch_from_tushare_falls_back_to_index_daily(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePro:
        def daily(self, **kwargs):
            return pd.DataFrame()

        def index_daily(self, **kwargs):
            return pd.DataFrame([
                {
                    "ts_code": "000300.SH",
                    "trade_date": "20260106",
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.8,
                    "close": 10.2,
                    "vol": 123456.0,
                }
            ])

    monkeypatch.setattr("quant_balance.data.tushare_loader.load_tushare_token", lambda: "token")
    monkeypatch.setitem(
        sys.modules,
        "tushare",
        SimpleNamespace(pro_api=lambda token: FakePro()),
    )

    rows = _fetch_from_tushare("000300.SH", "20260101", "20260131")

    assert rows == [
        ("000300.SH", "20260106", 10.0, 10.5, 9.8, 10.2, 123456.0)
    ]


def test_fetch_minute_from_tushare_falls_back_to_idx_mins(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePro:
        def stk_mins(self, **kwargs):
            return pd.DataFrame()

        def idx_mins(self, **kwargs):
            return pd.DataFrame([
                {
                    "ts_code": "000300.SH",
                    "trade_time": "2026-01-06 09:31:00",
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.8,
                    "close": 10.2,
                    "vol": 1234.0,
                }
            ])

    monkeypatch.setattr("quant_balance.data.tushare_loader.load_tushare_token", lambda: "token")
    monkeypatch.setitem(
        sys.modules,
        "tushare",
        SimpleNamespace(pro_api=lambda token: FakePro()),
    )

    rows = _fetch_minute_from_tushare("000300.SH", "2026-01-06 09:30:00", "2026-01-06 15:00:00", "1min")

    assert rows == [
        ("000300.SH", "2026-01-06 09:31:00", "1min", 10.0, 10.5, 9.8, 10.2, 1234.0)
    ]
