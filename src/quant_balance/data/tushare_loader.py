"""Tushare 日线数据加载 + SQLite 缓存。"""

from __future__ import annotations

import sqlite3
import tomllib
from datetime import datetime
from pathlib import Path

from quant_balance.core.models import MarketBar

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


class DataLoadError(ValueError):
    """数据加载异常。"""


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """获取 SQLite 连接，首次时自动建表。"""
    path = db_path or CACHE_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(_CREATE_TABLE_SQL)
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


def _save_to_cache(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    """把 Tushare 拉回的数据写入缓存。"""
    conn.executemany(
        "INSERT OR REPLACE INTO daily_bars "
        "(ts_code, trade_date, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
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


def _to_yyyymmdd(iso_date: str) -> str:
    """将 YYYY-MM-DD 转换为 YYYYMMDD。"""
    return iso_date.replace("-", "")


def _rows_to_bars(rows: list[tuple], symbol: str) -> list[MarketBar]:
    """把数据库行转换为 MarketBar 列表（按日期升序）。"""
    bars: list[MarketBar] = []
    for row in sorted(rows, key=lambda r: r[1]):
        trade_date = datetime.strptime(row[1], "%Y%m%d").date()
        bars.append(
            MarketBar(
                symbol=symbol,
                date=trade_date,
                open=row[2],
                high=row[3],
                low=row[4],
                close=row[5],
                volume=row[6],
            )
        )
    return bars


def load_bars(
    ts_code: str,
    start_date: str,
    end_date: str,
    *,
    db_path: Path | None = None,
) -> list[MarketBar]:
    """加载日线行情：先查 SQLite 缓存，未命中则从 Tushare 拉取后写入缓存。

    参数均为原始值，不依赖任何请求对象：
    - ts_code: Tushare 股票代码，如 "600519.SH"
    - start_date: 起始日期，YYYY-MM-DD 格式
    - end_date: 结束日期，YYYY-MM-DD 格式
    """
    start = _to_yyyymmdd(start_date)
    end = _to_yyyymmdd(end_date)

    conn = _get_connection(db_path)
    try:
        cached = _query_cache(conn, ts_code, start, end)
        if cached:
            bars = _rows_to_bars(cached, ts_code)
        else:
            rows = _fetch_from_tushare(ts_code, start, end)
            if rows:
                _save_to_cache(conn, rows)
            bars = _rows_to_bars(rows, ts_code)
    finally:
        conn.close()

    if not bars:
        raise DataLoadError(
            f"在 {start_date} ~ {end_date} 期间未找到 {ts_code} 的行情数据，"
            "请检查股票代码和日期范围是否正确。"
        )
    return bars
