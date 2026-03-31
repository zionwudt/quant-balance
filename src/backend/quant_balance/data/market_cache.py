"""非 Tushare 行情数据的本地缓存。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from quant_balance.data.common import CACHE_DB_PATH

_CREATE_PROVIDER_DAILY_SQL = """
CREATE TABLE IF NOT EXISTS provider_daily_bars (
    provider TEXT NOT NULL,
    ts_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    adjust TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    PRIMARY KEY (provider, ts_code, trade_date, adjust)
);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """获取 provider 行情缓存连接。"""
    from quant_balance.data.connection import get_shared_connection

    conn = get_shared_connection(db_path)
    conn.execute(_CREATE_PROVIDER_DAILY_SQL)
    return conn


def query_daily_bars(
    conn: sqlite3.Connection,
    *,
    provider: str,
    ts_code: str,
    start_date: str,
    end_date: str,
    adjust: str,
) -> list[tuple]:
    """按 provider 查询缓存中的日线数据。"""
    cursor = conn.execute(
        "SELECT ts_code, trade_date, open, high, low, close, volume "
        "FROM provider_daily_bars "
        "WHERE provider = ? AND ts_code = ? AND trade_date >= ? AND trade_date <= ? AND adjust = ? "
        "ORDER BY trade_date",
        (provider, ts_code, start_date, end_date, adjust),
    )
    return cursor.fetchall()


def save_daily_bars(
    conn: sqlite3.Connection,
    *,
    provider: str,
    adjust: str,
    rows: list[tuple],
) -> None:
    """保存 provider 行情缓存。"""
    conn.executemany(
        "INSERT OR REPLACE INTO provider_daily_bars "
        "(provider, ts_code, trade_date, adjust, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (provider, row[0], row[1], adjust, row[2], row[3], row[4], row[5], row[6])
            for row in rows
        ],
    )
    conn.commit()

