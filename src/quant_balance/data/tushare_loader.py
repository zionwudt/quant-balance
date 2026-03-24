"""Tushare 日线数据加载 + SQLite 缓存。"""

from __future__ import annotations

import sqlite3
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.toml"
CACHE_DB_PATH = Path.home() / ".quant_balance" / "cache.db"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS daily_bars (
    ts_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    PRIMARY KEY (ts_code, trade_date)
);
"""

_CREATE_ADJ_FACTOR_SQL = """
CREATE TABLE IF NOT EXISTS daily_adj_factors (
    ts_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    adj_factor REAL NOT NULL,
    PRIMARY KEY (ts_code, trade_date)
);
"""

class DataLoadError(ValueError):
    """数据加载异常。"""


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """获取 SQLite 连接，首次时自动建表。"""
    path = db_path or CACHE_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(_CREATE_TABLE_SQL)
    conn.execute(_CREATE_ADJ_FACTOR_SQL)
    return conn


def _query_cache(
    conn: sqlite3.Connection,
    ts_code: str,
    start_date: str,
    end_date: str,
) -> list[tuple]:
    """从缓存查询日线数据。日期格式 YYYYMMDD。"""
    cursor = conn.execute(
        "SELECT ts_code, trade_date, open, high, low, close, volume "
        "FROM daily_bars "
        "WHERE ts_code = ? AND trade_date >= ? AND trade_date <= ? "
        "ORDER BY trade_date",
        (ts_code, start_date, end_date),
    )
    return cursor.fetchall()


def _query_adj_factor_cache(
    conn: sqlite3.Connection,
    ts_code: str,
    start_date: str,
    end_date: str,
) -> list[tuple]:
    """从缓存查询复权因子。日期格式 YYYYMMDD。"""

    cursor = conn.execute(
        "SELECT ts_code, trade_date, adj_factor "
        "FROM daily_adj_factors "
        "WHERE ts_code = ? AND trade_date >= ? AND trade_date <= ? "
        "ORDER BY trade_date",
        (ts_code, start_date, end_date),
    )
    return cursor.fetchall()


def _save_to_cache(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    """把 Tushare 拉回的数据写入缓存。"""
    conn.executemany(
        "INSERT OR REPLACE INTO daily_bars "
        "(ts_code, trade_date, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def _save_adj_factors_to_cache(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    """把复权因子写入缓存。"""

    conn.executemany(
        "INSERT OR REPLACE INTO daily_adj_factors "
        "(ts_code, trade_date, adj_factor) "
        "VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def _load_tushare_token() -> str:
    """从 config/config.toml 读取 Tushare token。"""
    if not _CONFIG_PATH.exists():
        raise DataLoadError(
            f"未找到配置文件 {_CONFIG_PATH}，"
            "请复制 config/config.example.toml 为 config/config.toml 并填入你的 Tushare token。"
        )
    with open(_CONFIG_PATH, "rb") as f:
        config = tomllib.load(f)
    token = (config.get("tushare") or {}).get("token", "")
    if not token or token == "你的token":
        raise DataLoadError(
            "config/config.toml 中的 [tushare] token 未设置，"
            "请填入你的 Tushare token。获取方式：https://tushare.pro/register"
        )
    return token


def _fetch_from_tushare(
    ts_code: str,
    start_date: str,
    end_date: str,
) -> list[tuple]:
    """通过 Tushare Pro 拉取日线数据。"""
    try:
        import tushare as ts
    except ImportError as exc:
        raise DataLoadError(
            "需要安装 tushare 才能获取行情数据，请运行：pip install tushare"
        ) from exc

    token = _load_tushare_token()
    pro = ts.pro_api(token)

    df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    if df is None or df.empty:
        return []

    rows: list[tuple] = []
    for _, row in df.iterrows():
        rows.append((
            row["ts_code"],
            row["trade_date"],
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
            float(row["vol"]),
        ))
    return rows


def _fetch_adj_factors_from_tushare(
    ts_code: str,
    start_date: str,
    end_date: str,
) -> list[tuple]:
    """通过 Tushare Pro 拉取复权因子。"""

    try:
        import tushare as ts
    except ImportError as exc:
        raise DataLoadError(
            "需要安装 tushare 才能获取行情数据，请运行：pip install tushare"
        ) from exc

    token = _load_tushare_token()
    pro = ts.pro_api(token)

    df = pro.adj_factor(ts_code=ts_code, start_date=start_date, end_date=end_date)
    if df is None or df.empty:
        return []

    rows: list[tuple] = []
    for _, row in df.iterrows():
        rows.append((
            row["ts_code"],
            row["trade_date"],
            float(row["adj_factor"]),
        ))
    return rows


def _to_yyyymmdd(iso_date: str) -> str:
    """将 YYYY-MM-DD 转换为 YYYYMMDD。"""
    return iso_date.replace("-", "")


def load_dataframe(
    ts_code: str,
    start_date: str,
    end_date: str,
    *,
    adjust: Literal["none", "qfq"] = "qfq",
    db_path: Path | None = None,
) -> pd.DataFrame:
    """加载日线行情，返回 backtesting.py / vectorbt 通用的 DataFrame 格式。

    返回列: Open, High, Low, Close, Volume
    索引: DatetimeIndex（按日期升序）

    参数:
    - ts_code: Tushare 股票代码，如 "600519.SH"
    - start_date / end_date: YYYY-MM-DD 格式
    - adjust: "qfq" 前复权（默认），"none" 不复权
    """
    start = _to_yyyymmdd(start_date)
    end = _to_yyyymmdd(end_date)

    conn = _get_connection(db_path)
    try:
        cached_prices = _query_cache(conn, ts_code, start, end)
        if cached_prices:
            price_rows = cached_prices
        else:
            price_rows = _fetch_from_tushare(ts_code, start, end)
            if price_rows:
                _save_to_cache(conn, price_rows)

        factor_rows: list[tuple] = []
        if adjust == "qfq" and price_rows:
            factor_rows = _query_adj_factor_cache(conn, ts_code, start, end)
            if len(factor_rows) < len(price_rows):
                fresh = _fetch_adj_factors_from_tushare(ts_code, start, end)
                if fresh:
                    _save_adj_factors_to_cache(conn, fresh)
                    factor_rows = _query_adj_factor_cache(conn, ts_code, start, end)
    finally:
        conn.close()

    if not price_rows:
        raise DataLoadError(
            f"在 {start_date} ~ {end_date} 期间未找到 {ts_code} 的行情数据，"
            "请检查股票代码和日期范围是否正确。"
        )

    sorted_rows = sorted(price_rows, key=lambda r: r[1])

    if adjust == "qfq" and factor_rows:
        factor_by_date = {row[1]: row[2] for row in factor_rows}
        latest_date = sorted_rows[-1][1]
        latest_factor = factor_by_date.get(latest_date)
        if latest_factor is None or latest_factor <= 0:
            raise DataLoadError(f"{ts_code} 在 {latest_date} 缺少有效复权因子。")

        records = []
        for row in sorted_rows:
            adj = factor_by_date.get(row[1])
            if adj is None or adj <= 0:
                raise DataLoadError(f"{ts_code} 在 {row[1]} 缺少有效复权因子。")
            scale = adj / latest_factor
            records.append({
                "Date": datetime.strptime(row[1], "%Y%m%d"),
                "Open": row[2] * scale,
                "High": row[3] * scale,
                "Low": row[4] * scale,
                "Close": row[5] * scale,
                "Volume": row[6],
            })
    else:
        records = []
        for row in sorted_rows:
            records.append({
                "Date": datetime.strptime(row[1], "%Y%m%d"),
                "Open": row[2],
                "High": row[3],
                "Low": row[4],
                "Close": row[5],
                "Volume": row[6],
            })

    df = pd.DataFrame(records)
    df.set_index("Date", inplace=True)
    return df
