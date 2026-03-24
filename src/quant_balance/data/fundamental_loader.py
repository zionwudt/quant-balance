"""财务数据加载 —— 按公告日对齐，防止未来函数。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from quant_balance.data.tushare_loader import (
    CACHE_DB_PATH,
    DataLoadError,
    _load_tushare_token,
)

_CREATE_FINANCIAL_SQL = """
CREATE TABLE IF NOT EXISTS financial_data (
    ts_code    TEXT NOT NULL,
    ann_date   TEXT NOT NULL,
    end_date   TEXT NOT NULL,
    eps        REAL,
    bps        REAL,
    roe        REAL,
    net_profit REAL,
    total_revenue REAL,
    PRIMARY KEY (ts_code, ann_date, end_date)
);
"""

_CREATE_FETCH_LOG_SQL = """
CREATE TABLE IF NOT EXISTS financial_fetch_log (
    ts_code TEXT PRIMARY KEY
);
"""


@dataclass(slots=True)
class FinancialSnapshot:
    """截至某公告日的最新财务数据快照。"""

    ts_code: str
    ann_date: str       # 公告日 YYYYMMDD
    end_date: str       # 报告期末 YYYYMMDD
    eps: float | None   # 每股收益
    bps: float | None   # 每股净资产
    roe: float | None   # 净资产收益率
    net_profit: float | None     # 净利润
    total_revenue: float | None  # 营业总收入


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or CACHE_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(_CREATE_FINANCIAL_SQL)
    conn.execute(_CREATE_FETCH_LOG_SQL)
    return conn


def _has_fetched(conn: sqlite3.Connection, ts_code: str) -> bool:
    """该股票是否已从 Tushare 拉取过财务数据。"""
    row = conn.execute(
        "SELECT 1 FROM financial_fetch_log WHERE ts_code = ?", (ts_code,)
    ).fetchone()
    return row is not None


def _fetch_and_cache_financial(conn: sqlite3.Connection, ts_code: str) -> None:
    """从 Tushare 拉取指定股票的财务指标并写入缓存。"""
    try:
        import tushare as ts
    except ImportError as exc:
        raise DataLoadError(
            "需要安装 tushare 才能获取财务数据，请运行：pip install tushare"
        ) from exc

    token = _load_tushare_token()
    pro = ts.pro_api(token)

    df = pro.fina_indicator(
        ts_code=ts_code,
        fields="ts_code,ann_date,end_date,eps,bps,roe,net_profit,total_revenue",
    )
    if df is None or df.empty:
        return

    rows: list[tuple] = []
    for _, r in df.iterrows():
        ann = r.get("ann_date")
        if not ann or str(ann) == "nan":
            continue
        rows.append((
            r["ts_code"],
            str(ann).split(".")[0],
            str(r.get("end_date", "")).split(".")[0],
            float(r["eps"]) if r.get("eps") and str(r["eps"]) != "nan" else None,
            float(r["bps"]) if r.get("bps") and str(r["bps"]) != "nan" else None,
            float(r["roe"]) if r.get("roe") and str(r["roe"]) != "nan" else None,
            float(r["net_profit"]) if r.get("net_profit") and str(r["net_profit"]) != "nan" else None,
            float(r["total_revenue"]) if r.get("total_revenue") and str(r["total_revenue"]) != "nan" else None,
        ))

    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO financial_data "
            "(ts_code, ann_date, end_date, eps, bps, roe, net_profit, total_revenue) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()

    conn.execute(
        "INSERT OR REPLACE INTO financial_fetch_log (ts_code) VALUES (?)",
        (ts_code,),
    )
    conn.commit()


def load_financial_at(
    symbol: str,
    as_of_date: str,
    *,
    db_path: Path | None = None,
) -> FinancialSnapshot | None:
    """返回截至 as_of_date 已公告的最新财务数据。

    绝不使用 end_date 做时间筛选，只按 ann_date <= as_of_date 过滤。

    参数:
        symbol: Tushare 股票代码，如 "600519.SH"
        as_of_date: 查询基准日期，YYYY-MM-DD 格式
    返回:
        FinancialSnapshot 或 None（无已公告数据时）
    """
    yyyymmdd = as_of_date.replace("-", "")

    conn = _get_connection(db_path)
    try:
        if not _has_fetched(conn, symbol):
            _fetch_and_cache_financial(conn, symbol)

        row = conn.execute(
            "SELECT ts_code, ann_date, end_date, eps, bps, roe, net_profit, total_revenue "
            "FROM financial_data "
            "WHERE ts_code = ? AND ann_date <= ? "
            "ORDER BY ann_date DESC LIMIT 1",
            (symbol, yyyymmdd),
        ).fetchone()

        if row is None:
            return None

        return FinancialSnapshot(
            ts_code=row[0],
            ann_date=row[1],
            end_date=row[2],
            eps=row[3],
            bps=row[4],
            roe=row[5],
            net_profit=row[6],
            total_revenue=row[7],
        )
    finally:
        conn.close()
