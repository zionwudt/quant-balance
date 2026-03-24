"""历史时点股票池构建 —— 防止幸存者偏差。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from quant_balance.data.tushare_loader import (
    CACHE_DB_PATH,
    DataLoadError,
    _load_tushare_token,
)

_CREATE_STOCK_LIST_SQL = """
CREATE TABLE IF NOT EXISTS stock_list (
    ts_code   TEXT PRIMARY KEY,
    name      TEXT,
    list_date TEXT,
    delist_date TEXT,
    industry  TEXT,
    market    TEXT
);
"""


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or CACHE_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(_CREATE_STOCK_LIST_SQL)
    return conn


def _is_cache_populated(conn: sqlite3.Connection) -> bool:
    """stock_list 表中是否已有数据。"""
    row = conn.execute("SELECT COUNT(*) FROM stock_list").fetchone()
    return row[0] > 0


def _fetch_and_cache_stock_list(conn: sqlite3.Connection) -> None:
    """从 Tushare 全量拉取上市 + 退市股票并写入缓存。"""
    try:
        import tushare as ts
    except ImportError as exc:
        raise DataLoadError(
            "需要安装 tushare 才能获取股票列表，请运行：pip install tushare"
        ) from exc

    token = _load_tushare_token()
    pro = ts.pro_api(token)

    rows: list[tuple] = []
    for status in ("L", "D", "P"):  # 上市、退市、暂停上市
        df = pro.stock_basic(list_status=status,
                             fields="ts_code,name,list_date,delist_date,industry,market")
        if df is not None and not df.empty:
            for _, r in df.iterrows():
                rows.append((
                    r["ts_code"],
                    r.get("name", ""),
                    r.get("list_date", ""),
                    r.get("delist_date") if r.get("delist_date") and str(r.get("delist_date")) != "nan" else None,
                    r.get("industry", ""),
                    r.get("market", ""),
                ))

    conn.executemany(
        "INSERT OR REPLACE INTO stock_list "
        "(ts_code, name, list_date, delist_date, industry, market) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def get_pool_at_date(
    date: str,
    *,
    db_path: Path | None = None,
) -> list[str]:
    """返回指定历史日期当天处于上市状态的股票代码列表。

    参数:
        date: 日期，YYYY-MM-DD 格式（如 "2015-01-01"）
    返回:
        ts_code 列表，如 ["600519.SH", "000001.SZ", ...]
    """
    yyyymmdd = date.replace("-", "")

    conn = _get_connection(db_path)
    try:
        if not _is_cache_populated(conn):
            _fetch_and_cache_stock_list(conn)

        cursor = conn.execute(
            "SELECT ts_code FROM stock_list "
            "WHERE list_date <= ? AND (delist_date IS NULL OR delist_date > ?) "
            "ORDER BY ts_code",
            (yyyymmdd, yyyymmdd),
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()
