"""可转债日线数据加载 + SQLite 缓存。"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from quant_balance.data.common import CACHE_DB_PATH, DataLoadError, load_tushare_token
from quant_balance.data.tushare_loader import load_dataframe as load_stock_dataframe
from quant_balance.logging_utils import get_logger, log_event

_CREATE_CB_DAILY_SQL = """
CREATE TABLE IF NOT EXISTS cb_daily_bars (
    ts_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    amount REAL,
    bond_value REAL,
    bond_over_rate REAL,
    cb_value REAL,
    cb_over_rate REAL,
    PRIMARY KEY (ts_code, trade_date)
);
"""

_CREATE_CB_BASIC_SQL = """
CREATE TABLE IF NOT EXISTS cb_basic_info (
    ts_code TEXT PRIMARY KEY,
    bond_short_name TEXT,
    stk_code TEXT,
    stk_short_name TEXT
);
"""

logger = get_logger(__name__)


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or CACHE_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(_CREATE_CB_DAILY_SQL)
    conn.execute(_CREATE_CB_BASIC_SQL)
    return conn


def _query_daily_cache(
    conn: sqlite3.Connection,
    ts_code: str,
    start_date: str,
    end_date: str,
) -> list[tuple]:
    cursor = conn.execute(
        "SELECT ts_code, trade_date, open, high, low, close, volume, amount, bond_value, bond_over_rate, cb_value, cb_over_rate "
        "FROM cb_daily_bars "
        "WHERE ts_code = ? AND trade_date >= ? AND trade_date <= ? "
        "ORDER BY trade_date",
        (ts_code, start_date, end_date),
    )
    return cursor.fetchall()


def _query_basic_cache(
    conn: sqlite3.Connection,
    ts_code: str,
) -> tuple | None:
    cursor = conn.execute(
        "SELECT ts_code, bond_short_name, stk_code, stk_short_name "
        "FROM cb_basic_info WHERE ts_code = ?",
        (ts_code,),
    )
    return cursor.fetchone()


def _save_daily_to_cache(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO cb_daily_bars "
        "(ts_code, trade_date, open, high, low, close, volume, amount, bond_value, bond_over_rate, cb_value, cb_over_rate) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def _save_basic_to_cache(conn: sqlite3.Connection, row: tuple) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO cb_basic_info "
        "(ts_code, bond_short_name, stk_code, stk_short_name) "
        "VALUES (?, ?, ?, ?)",
        row,
    )
    conn.commit()


def _fetch_cb_daily_from_tushare(
    ts_code: str,
    start_date: str,
    end_date: str,
) -> list[tuple]:
    try:
        import tushare as ts
    except ImportError as exc:
        raise DataLoadError("需要安装 tushare 才能获取可转债行情数据，请运行：pip install tushare") from exc

    token = load_tushare_token()
    pro = ts.pro_api(token)
    df = pro.cb_daily(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
        fields="ts_code,trade_date,open,high,low,close,vol,amount,bond_value,bond_over_rate,cb_value,cb_over_rate",
    )
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
            _optional_float(row.get("amount")),
            _optional_float(row.get("bond_value")),
            _optional_float(row.get("bond_over_rate")),
            _optional_float(row.get("cb_value")),
            _optional_float(row.get("cb_over_rate")),
        ))
    return rows


def _fetch_cb_basic_from_tushare(ts_code: str) -> tuple | None:
    try:
        import tushare as ts
    except ImportError as exc:
        raise DataLoadError("需要安装 tushare 才能获取可转债基础信息，请运行：pip install tushare") from exc

    token = load_tushare_token()
    pro = ts.pro_api(token)
    df = pro.cb_basic(
        ts_code=ts_code,
        fields="ts_code,bond_short_name,stk_code,stk_short_name",
    )
    if df is None or df.empty:
        return None

    first = df.iloc[0]
    return (
        str(first["ts_code"]),
        str(first.get("bond_short_name") or ""),
        str(first.get("stk_code") or ""),
        str(first.get("stk_short_name") or ""),
    )


def _to_yyyymmdd(iso_date: str) -> str:
    return iso_date.replace("-", "")


def load_dataframe(
    ts_code: str,
    start_date: str,
    end_date: str,
    *,
    db_path: Path | None = None,
) -> pd.DataFrame:
    """加载可转债日线，返回兼容现有回测/筛选流程的 DataFrame。"""

    start = _to_yyyymmdd(start_date)
    end = _to_yyyymmdd(end_date)

    conn = _get_connection(db_path)
    try:
        daily_rows = _query_daily_cache(conn, ts_code, start, end)
        if daily_rows:
            log_event(
                logger,
                "CACHE_HIT",
                data_provider="tushare",
                dataset="cb_daily_bars",
                symbol=ts_code,
                start_date=start_date,
                end_date=end_date,
                rows_count=len(daily_rows),
            )
        else:
            log_event(
                logger,
                "CACHE_MISS",
                data_provider="tushare",
                dataset="cb_daily_bars",
                symbol=ts_code,
                start_date=start_date,
                end_date=end_date,
            )
            daily_rows = _fetch_cb_daily_from_tushare(ts_code, start, end)
            if daily_rows:
                _save_daily_to_cache(conn, daily_rows)

        basic_row = _query_basic_cache(conn, ts_code)
        if basic_row is not None:
            log_event(
                logger,
                "CACHE_HIT",
                data_provider="tushare",
                dataset="cb_basic_info",
                symbol=ts_code,
            )
        else:
            log_event(
                logger,
                "CACHE_MISS",
                data_provider="tushare",
                dataset="cb_basic_info",
                symbol=ts_code,
            )
            basic_row = _fetch_cb_basic_from_tushare(ts_code)
            if basic_row is not None:
                _save_basic_to_cache(conn, basic_row)
    finally:
        conn.close()

    if not daily_rows:
        raise DataLoadError(
            f"在 {start_date} ~ {end_date} 期间未找到 {ts_code} 的可转债行情数据，"
            "请检查债券代码、日期范围和 Tushare 权限。"
        )
    if basic_row is None:
        raise DataLoadError(f"未找到 {ts_code} 的可转债基础信息。")

    _, bond_short_name, underlying_symbol, underlying_name = basic_row
    underlying_close_map: dict[str, float] = {}
    if underlying_symbol:
        try:
            underlying_df = load_stock_dataframe(
                underlying_symbol,
                start_date,
                end_date,
                adjust="none",
                db_path=db_path,
            )
            underlying_close_map = {
                index.strftime("%Y%m%d"): float(row["Close"])
                for index, row in underlying_df.iterrows()
            }
        except DataLoadError as exc:
            log_event(
                logger,
                "CB_DERIVED_FIELD_SKIP",
                level=logging.WARNING,
                symbol=ts_code,
                underlying_symbol=underlying_symbol,
                start_date=start_date,
                end_date=end_date,
                reason=str(exc),
            )

    records = []
    for row in sorted(daily_rows, key=lambda item: item[1]):
        trade_date = row[1]
        underlying_close = underlying_close_map.get(trade_date)
        conversion_value = row[10]
        conversion_price = None
        if underlying_close is not None and conversion_value is not None and conversion_value > 0:
            conversion_price = underlying_close * 100 / conversion_value

        records.append({
            "Date": datetime.strptime(trade_date, "%Y%m%d"),
            "Open": row[2],
            "High": row[3],
            "Low": row[4],
            "Close": row[5],
            "Volume": row[6],
            "Amount": row[7],
            "BondValue": row[8],
            "PureBondPremiumRate": row[9],
            "ConversionValue": row[10],
            "ConversionPremiumRate": row[11],
            "UnderlyingClose": underlying_close,
            "ConversionPrice": conversion_price,
        })

    df = pd.DataFrame(records)
    df.set_index("Date", inplace=True)
    df.attrs["data_provider"] = "tushare"
    df.attrs["asset_type"] = "convertible_bond"
    df.attrs["bond_short_name"] = bond_short_name
    df.attrs["underlying_symbol"] = underlying_symbol
    df.attrs["underlying_name"] = underlying_name
    return df


def _optional_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)
