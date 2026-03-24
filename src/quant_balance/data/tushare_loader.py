"""Tushare 日线数据加载 + SQLite 缓存。"""

from __future__ import annotations

import sqlite3
import tomllib
from dataclasses import dataclass
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

_CREATE_ADJ_FACTOR_SQL = """
CREATE TABLE IF NOT EXISTS daily_adj_factors (
    ts_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    adj_factor REAL NOT NULL,
    PRIMARY KEY (ts_code, trade_date)
);
"""


@dataclass(slots=True)
class LoadedBarViews:
    """同一时间窗口下的双轨价格视图。

    `trade_bars` 保留不复权价格，用于撮合、持仓成本和盈亏计算；
    `indicator_bars` 则锚定到本次回测窗口末尾，供技术指标与策略信号使用。
    """

    trade_bars: list[MarketBar]
    indicator_bars: list[MarketBar]


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


def _rows_to_forward_adjusted_bars(
    price_rows: list[tuple],
    factor_rows: list[tuple],
    symbol: str,
) -> list[MarketBar]:
    """把不复权行情和复权因子转换为锚定窗口末尾的前复权序列。"""

    if not price_rows:
        return []

    factor_by_date = {row[1]: row[2] for row in factor_rows}
    sorted_rows = sorted(price_rows, key=lambda row: row[1])
    latest_trade_date = sorted_rows[-1][1]
    latest_factor = factor_by_date.get(latest_trade_date)
    if latest_factor is None or latest_factor <= 0:
        raise DataLoadError(f"{symbol} 在 {latest_trade_date} 缺少有效复权因子，无法生成前复权价格。")

    bars: list[MarketBar] = []
    for row in sorted_rows:
        trade_date = row[1]
        adj_factor = factor_by_date.get(trade_date)
        if adj_factor is None or adj_factor <= 0:
            raise DataLoadError(f"{symbol} 在 {trade_date} 缺少有效复权因子，无法生成前复权价格。")

        scale = adj_factor / latest_factor
        bar_date = datetime.strptime(trade_date, "%Y%m%d").date()
        bars.append(
            MarketBar(
                symbol=symbol,
                date=bar_date,
                open=row[2] * scale,
                high=row[3] * scale,
                low=row[4] * scale,
                close=row[5] * scale,
                volume=row[6],
            )
        )
    return bars


def load_bar_views(
    ts_code: str,
    start_date: str,
    end_date: str,
    *,
    db_path: Path | None = None,
) -> LoadedBarViews:
    """加载回测所需双轨价格视图。"""

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

        factor_rows = _query_adj_factor_cache(conn, ts_code, start, end)
        if price_rows and len(factor_rows) < len(price_rows):
            fresh_factor_rows = _fetch_adj_factors_from_tushare(ts_code, start, end)
            if fresh_factor_rows:
                _save_adj_factors_to_cache(conn, fresh_factor_rows)
                factor_rows = _query_adj_factor_cache(conn, ts_code, start, end)
    finally:
        conn.close()

    trade_bars = _rows_to_bars(price_rows, ts_code)
    if not trade_bars:
        raise DataLoadError(
            f"在 {start_date} ~ {end_date} 期间未找到 {ts_code} 的行情数据，"
            "请检查股票代码和日期范围是否正确。"
        )

    indicator_bars = trade_bars
    if factor_rows:
        indicator_bars = _rows_to_forward_adjusted_bars(price_rows, factor_rows, ts_code)

    return LoadedBarViews(trade_bars=trade_bars, indicator_bars=indicator_bars)


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
    return load_bar_views(
        ts_code,
        start_date,
        end_date,
        db_path=db_path,
    ).trade_bars
