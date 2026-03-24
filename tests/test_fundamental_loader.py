"""load_financial_at 单元测试 —— 未来函数防护。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from quant_balance.data.fundamental_loader import (
    FinancialSnapshot,
    _CREATE_FETCH_LOG_SQL,
    _CREATE_FINANCIAL_SQL,
    load_financial_at,
)


def _seed_db(db_path: Path, rows: list[tuple], fetched_symbols: list[str]) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(_CREATE_FINANCIAL_SQL)
    conn.execute(_CREATE_FETCH_LOG_SQL)
    conn.executemany(
        "INSERT INTO financial_data "
        "(ts_code, ann_date, end_date, eps, bps, roe, net_profit, total_revenue) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.executemany(
        "INSERT INTO financial_fetch_log (ts_code) VALUES (?)",
        [(s,) for s in fetched_symbols],
    )
    conn.commit()
    conn.close()


# ── 测试数据 ──────────────────────────────────────────────
# 模拟贵州茅台的财务公告时间线：
#   Q3 2023 报告期末 20230930，公告日 20231028
#   Q4 2023 报告期末 20231231，公告日 20240420（次年4月才公告）
#   Q1 2024 报告期末 20240331，公告日 20240426

FINANCIAL_ROWS = [
    ("600519.SH", "20231028", "20230930", 40.5, 200.0, 25.8, 5000000000, 10000000000),
    ("600519.SH", "20240420", "20231231", 55.2, 220.0, 28.1, 7500000000, 15000000000),
    ("600519.SH", "20240426", "20240331", 12.3, 225.0, 6.5,  1800000000, 4000000000),
]


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test_cache.db"
    _seed_db(p, FINANCIAL_ROWS, ["600519.SH", "999999.SH"])
    return p


class TestLoadFinancialAt:
    """核心场景测试。"""

    def test_jan_query_returns_q3_not_q4(self, db_path: Path) -> None:
        """2024年1月查询时，Q4数据尚未公告（4月才公告），应返回Q3数据。"""
        snap = load_financial_at("600519.SH", "2024-01-15", db_path=db_path)
        assert snap is not None
        assert snap.end_date == "20230930"  # Q3
        assert snap.ann_date == "20231028"

    def test_never_returns_future_announcement(self, db_path: Path) -> None:
        """2024年3月查询，Q4公告日为4月20日，不应返回。"""
        snap = load_financial_at("600519.SH", "2024-03-15", db_path=db_path)
        assert snap is not None
        assert snap.ann_date <= "20240315"
        assert snap.end_date == "20230930"

    def test_returns_q4_after_announcement(self, db_path: Path) -> None:
        """2024年4月20日（含）之后应能获取Q4数据。"""
        snap = load_financial_at("600519.SH", "2024-04-20", db_path=db_path)
        assert snap is not None
        assert snap.end_date == "20231231"
        assert snap.ann_date == "20240420"

    def test_returns_latest_when_multiple_announced(self, db_path: Path) -> None:
        """2024年5月时Q4和Q1都已公告，应返回最近公告的Q1。"""
        snap = load_financial_at("600519.SH", "2024-05-01", db_path=db_path)
        assert snap is not None
        assert snap.end_date == "20240331"
        assert snap.ann_date == "20240426"

    def test_returns_none_before_any_announcement(self, db_path: Path) -> None:
        """在任何公告之前查询应返回 None。"""
        snap = load_financial_at("600519.SH", "2023-01-01", db_path=db_path)
        assert snap is None

    def test_returns_none_for_unknown_symbol(self, db_path: Path) -> None:
        """查询不存在的股票应返回 None。"""
        snap = load_financial_at("999999.SH", "2024-01-15", db_path=db_path)
        assert snap is None

    def test_announcement_day_boundary(self, db_path: Path) -> None:
        """公告当天应包含该数据（ann_date <= as_of_date）。"""
        snap = load_financial_at("600519.SH", "2023-10-28", db_path=db_path)
        assert snap is not None
        assert snap.ann_date == "20231028"

    def test_day_before_announcement_excluded(self, db_path: Path) -> None:
        """公告前一天不应返回该数据。"""
        snap = load_financial_at("600519.SH", "2023-10-27", db_path=db_path)
        assert snap is None

    def test_returns_financial_snapshot_type(self, db_path: Path) -> None:
        snap = load_financial_at("600519.SH", "2024-01-15", db_path=db_path)
        assert isinstance(snap, FinancialSnapshot)

    def test_cache_reuse(self, db_path: Path) -> None:
        """第二次调用应复用缓存。"""
        snap_1 = load_financial_at("600519.SH", "2024-01-15", db_path=db_path)
        snap_2 = load_financial_at("600519.SH", "2024-01-15", db_path=db_path)
        assert snap_1 == snap_2
