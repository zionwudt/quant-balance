"""Tushare 日线 / 分钟线数据加载 + SQLite 缓存。"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from quant_balance.data.common import CACHE_DB_PATH, DataLoadError, load_tushare_token
from quant_balance.logging_utils import get_logger, log_event

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

_CREATE_MINUTE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS minute_bars (
    ts_code TEXT NOT NULL,
    trade_time TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    PRIMARY KEY (ts_code, trade_time, timeframe)
);
"""

Timeframe = Literal["1d", "1min", "5min", "15min", "30min", "60min"]
MINUTE_TIMEFRAMES = {"1min", "5min", "15min", "30min", "60min"}

logger = get_logger(__name__)


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """获取 SQLite 连接，首次时自动建表。"""
    path = db_path or CACHE_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(_CREATE_TABLE_SQL)
    conn.execute(_CREATE_ADJ_FACTOR_SQL)
    conn.execute(_CREATE_MINUTE_TABLE_SQL)
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


def _query_minute_cache(
    conn: sqlite3.Connection,
    ts_code: str,
    start_time: str,
    end_time: str,
    timeframe: Timeframe,
) -> list[tuple]:
    """从缓存查询分钟线。时间格式 YYYY-MM-DD HH:MM:SS。"""

    cursor = conn.execute(
        "SELECT ts_code, trade_time, timeframe, open, high, low, close, volume "
        "FROM minute_bars "
        "WHERE ts_code = ? AND trade_time >= ? AND trade_time <= ? AND timeframe = ? "
        "ORDER BY trade_time",
        (ts_code, start_time, end_time, timeframe),
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


def _save_minute_bars_to_cache(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    """把分钟线写入缓存。"""

    conn.executemany(
        "INSERT OR REPLACE INTO minute_bars "
        "(ts_code, trade_time, timeframe, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


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

    token = load_tushare_token()
    pro = ts.pro_api(token)

    df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    if df is None or df.empty:
        df = pro.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
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


def _fetch_minute_from_tushare(
    ts_code: str,
    start_time: str,
    end_time: str,
    timeframe: Timeframe,
) -> list[tuple]:
    """通过 Tushare Pro 拉取分钟线。"""

    try:
        import tushare as ts
    except ImportError as exc:
        raise DataLoadError(
            "需要安装 tushare 才能获取行情数据，请运行：pip install tushare"
        ) from exc

    token = load_tushare_token()
    pro = ts.pro_api(token)

    df = pd.DataFrame()
    stock_fetcher = getattr(pro, "stk_mins", None)
    if callable(stock_fetcher):
        df = stock_fetcher(
            ts_code=ts_code,
            start_date=start_time,
            end_date=end_time,
            freq=timeframe,
        )
    elif hasattr(ts, "set_token") and hasattr(ts, "pro_bar"):
        ts.set_token(token)
        fallback = ts.pro_bar(
            ts_code=ts_code,
            start_date=start_time,
            end_date=end_time,
            freq=timeframe,
            asset="E",
        )
        df = fallback if fallback is not None else pd.DataFrame()

    if df is None or df.empty:
        index_fetcher = getattr(pro, "idx_mins", None)
        if callable(index_fetcher):
            df = index_fetcher(
                ts_code=ts_code,
                start_date=start_time,
                end_date=end_time,
                freq=timeframe,
            )
        elif hasattr(ts, "set_token") and hasattr(ts, "pro_bar"):
            ts.set_token(token)
            fallback = ts.pro_bar(
                ts_code=ts_code,
                start_date=start_time,
                end_date=end_time,
                freq=timeframe,
                asset="I",
            )
            df = fallback if fallback is not None else pd.DataFrame()
    if df is None or df.empty:
        return []

    rows: list[tuple] = []
    for _, row in df.iterrows():
        trade_time = pd.Timestamp(row["trade_time"]).strftime("%Y-%m-%d %H:%M:%S")
        rows.append((
            row["ts_code"],
            trade_time,
            timeframe,
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

    token = load_tushare_token()
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
    """将日期 / 时间文本归一化为 YYYYMMDD。"""
    try:
        return pd.Timestamp(str(iso_date).strip()).strftime("%Y%m%d")
    except Exception as exc:  # noqa: BLE001
        raise DataLoadError(f"无法解析日期 {iso_date!r}") from exc


def _normalize_timeframe(timeframe: str) -> Timeframe:
    normalized = str(timeframe or "1d").strip().lower()
    if normalized not in {"1d", *MINUTE_TIMEFRAMES}:
        raise DataLoadError("timeframe 当前仅支持 1d / 1min / 5min / 15min / 30min / 60min")
    return normalized  # type: ignore[return-value]


def _normalize_datetime_text(value: str, *, is_end: bool) -> str:
    text = str(value or "").strip()
    if not text:
        raise DataLoadError("分钟线请求必须提供有效的起止时间")

    has_time = " " in text or "T" in text
    try:
        normalized = pd.Timestamp(text)
    except Exception as exc:  # noqa: BLE001
        raise DataLoadError(f"无法解析时间 {value!r}") from exc
    if not has_time:
        normalized = normalized.replace(
            hour=23 if is_end else 0,
            minute=59 if is_end else 0,
            second=59 if is_end else 0,
        )
    return normalized.strftime("%Y-%m-%d %H:%M:%S")


def load_dataframe(
    ts_code: str,
    start_date: str,
    end_date: str,
    *,
    timeframe: Timeframe = "1d",
    adjust: Literal["none", "qfq"] = "qfq",
    db_path: Path | None = None,
) -> pd.DataFrame:
    """加载 Tushare 行情，返回 backtesting.py / vectorbt 通用的 DataFrame 格式。

    返回列: Open, High, Low, Close, Volume
    索引: DatetimeIndex（按时间升序）

    参数:
    - ts_code: Tushare 股票代码，如 "600519.SH"
    - start_date / end_date: 日线支持 YYYY-MM-DD；分钟线支持 YYYY-MM-DD 或 YYYY-MM-DD HH:MM[:SS]
    - timeframe: 1d / 1min / 5min / 15min / 30min / 60min
    - adjust: 日线支持 "qfq" 前复权（默认）/"none"；分钟线当前固定返回未复权价格
    """
    normalized_timeframe = _normalize_timeframe(timeframe)
    effective_adjust = adjust if normalized_timeframe == "1d" else "none"

    if normalized_timeframe == "1d":
        start = _to_yyyymmdd(start_date)
        end = _to_yyyymmdd(end_date)
    else:
        start = _normalize_datetime_text(start_date, is_end=False)
        end = _normalize_datetime_text(end_date, is_end=True)

    conn = _get_connection(db_path)
    try:
        factor_rows: list[tuple] = []
        if normalized_timeframe == "1d":
            cached_prices = _query_cache(conn, ts_code, start, end)
            if cached_prices:
                log_event(
                    logger,
                    "CACHE_HIT",
                    data_provider="tushare",
                    dataset="daily_bars",
                    symbol=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    timeframe=normalized_timeframe,
                    adjust=effective_adjust,
                    rows_count=len(cached_prices),
                )
                price_rows = cached_prices
            else:
                log_event(
                    logger,
                    "CACHE_MISS",
                    data_provider="tushare",
                    dataset="daily_bars",
                    symbol=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    timeframe=normalized_timeframe,
                    adjust=effective_adjust,
                )
                price_rows = _fetch_from_tushare(ts_code, start, end)
                if price_rows:
                    _save_to_cache(conn, price_rows)

            if effective_adjust == "qfq" and price_rows:
                factor_rows = _query_adj_factor_cache(conn, ts_code, start, end)
                if len(factor_rows) >= len(price_rows):
                    log_event(
                        logger,
                        "CACHE_HIT",
                        data_provider="tushare",
                        dataset="daily_adj_factors",
                        symbol=ts_code,
                        start_date=start_date,
                        end_date=end_date,
                        timeframe=normalized_timeframe,
                        adjust=effective_adjust,
                        rows_count=len(factor_rows),
                    )
                else:
                    log_event(
                        logger,
                        "CACHE_MISS",
                        data_provider="tushare",
                        dataset="daily_adj_factors",
                        symbol=ts_code,
                        start_date=start_date,
                        end_date=end_date,
                        timeframe=normalized_timeframe,
                        adjust=effective_adjust,
                        rows_count=len(factor_rows),
                        required_rows_count=len(price_rows),
                    )
                    fresh = _fetch_adj_factors_from_tushare(ts_code, start, end)
                    if fresh:
                        _save_adj_factors_to_cache(conn, fresh)
                        factor_rows = _query_adj_factor_cache(conn, ts_code, start, end)
        else:
            cached_prices = _query_minute_cache(conn, ts_code, start, end, normalized_timeframe)
            if cached_prices:
                log_event(
                    logger,
                    "CACHE_HIT",
                    data_provider="tushare",
                    dataset="minute_bars",
                    symbol=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    timeframe=normalized_timeframe,
                    adjust=effective_adjust,
                    rows_count=len(cached_prices),
                )
                price_rows = cached_prices
            else:
                log_event(
                    logger,
                    "CACHE_MISS",
                    data_provider="tushare",
                    dataset="minute_bars",
                    symbol=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    timeframe=normalized_timeframe,
                    adjust=effective_adjust,
                )
                price_rows = _fetch_minute_from_tushare(ts_code, start, end, normalized_timeframe)
                if price_rows:
                    _save_minute_bars_to_cache(conn, price_rows)
    finally:
        conn.close()

    if not price_rows:
        raise DataLoadError(
            f"在 {start_date} ~ {end_date} 期间未找到 {ts_code} 的 {normalized_timeframe} 行情数据，"
            "请检查股票代码和日期范围是否正确。"
        )

    sorted_rows = sorted(price_rows, key=lambda r: r[1])

    if normalized_timeframe == "1d" and effective_adjust == "qfq" and factor_rows:
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
            date_format = "%Y%m%d" if normalized_timeframe == "1d" else "%Y-%m-%d %H:%M:%S"
            trade_time = row[1]
            records.append({
                "Date": datetime.strptime(trade_time, date_format),
                "Open": row[-5],
                "High": row[-4],
                "Low": row[-3],
                "Close": row[-2],
                "Volume": row[-1],
            })

    df = pd.DataFrame(records)
    df.set_index("Date", inplace=True)
    df.attrs["data_provider"] = "tushare"
    df.attrs["timeframe"] = normalized_timeframe
    df.attrs["price_adjustment"] = effective_adjust
    return df
