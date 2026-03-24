"""get_pool_at_date 单元测试 —— 幸存者偏差防护。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from quant_balance.data.stock_pool import (
    _CREATE_STOCK_LIST_SQL,
    get_pool_at_date,
)


def _seed_db(db_path: Path, rows: list[tuple]) -> None:
    """向测试数据库插入 stock_list 数据。"""
    conn = sqlite3.connect(str(db_path))
    conn.execute(_CREATE_STOCK_LIST_SQL)
    conn.executemany(
        "INSERT INTO stock_list (ts_code, name, list_date, delist_date, industry, market) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


# ── 测试数据 ──────────────────────────────────────────────

STOCKS = [
    # ts_code, name, list_date, delist_date, industry, market
    ("000001.SZ", "平安银行", "19910403", None, "银行", "主板"),
    ("600519.SH", "贵州茅台", "20010827", None, "白酒", "主板"),
    ("300999.SZ", "金龙鱼",   "20201015", None, "食品", "创业板"),  # 2020 年上市
    ("000033.SZ", "退市新都", "19970618", "20170712", "房地产", "主板"),  # 已退市
    ("600432.SH", "退市吉恩", "20040120", "20180711", "有色金属", "主板"),  # 已退市
    ("688001.SH", "华兴源创", "20190722", None, "电子", "科创板"),  # 2019 年上市
]


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test_cache.db"
    _seed_db(p, STOCKS)
    return p


class TestGetPoolAtDate:
    """核心场景测试。"""

    def test_excludes_future_listed_stocks(self, db_path: Path) -> None:
        """2015-01-01 的股票池不应包含 2020 年才上市的金龙鱼。"""
        pool = get_pool_at_date("2015-01-01", db_path=db_path)
        assert "300999.SZ" not in pool

    def test_includes_later_delisted_stocks(self, db_path: Path) -> None:
        """2015-01-01 时退市新都和退市吉恩仍上市，应包含在池中。"""
        pool = get_pool_at_date("2015-01-01", db_path=db_path)
        assert "000033.SZ" in pool  # 2017 年才退市
        assert "600432.SH" in pool  # 2018 年才退市

    def test_excludes_already_delisted(self, db_path: Path) -> None:
        """2018-01-01 时退市新都已退市，不应出现。"""
        pool = get_pool_at_date("2018-01-01", db_path=db_path)
        assert "000033.SZ" not in pool

    def test_listing_day_included(self, db_path: Path) -> None:
        """上市当天应包含在股票池中。"""
        pool = get_pool_at_date("2001-08-27", db_path=db_path)
        assert "600519.SH" in pool

    def test_day_before_listing_excluded(self, db_path: Path) -> None:
        """上市前一天不应出现在池中。"""
        pool = get_pool_at_date("2001-08-26", db_path=db_path)
        assert "600519.SH" not in pool

    def test_delist_day_excluded(self, db_path: Path) -> None:
        """退市当天不应出现在池中（delist_date > date 用严格大于）。"""
        pool = get_pool_at_date("2017-07-12", db_path=db_path)
        assert "000033.SZ" not in pool

    def test_day_before_delist_included(self, db_path: Path) -> None:
        """退市前一天仍应在池中。"""
        pool = get_pool_at_date("2017-07-11", db_path=db_path)
        assert "000033.SZ" in pool

    def test_cache_reuse(self, db_path: Path) -> None:
        """第二次调用应复用缓存，不再触发 Tushare 请求。"""
        pool_1 = get_pool_at_date("2015-01-01", db_path=db_path)
        pool_2 = get_pool_at_date("2015-01-01", db_path=db_path)
        assert pool_1 == pool_2

    def test_result_is_sorted(self, db_path: Path) -> None:
        """返回列表应按 ts_code 排序。"""
        pool = get_pool_at_date("2015-01-01", db_path=db_path)
        assert pool == sorted(pool)

    def test_returns_list_of_strings(self, db_path: Path) -> None:
        pool = get_pool_at_date("2015-01-01", db_path=db_path)
        assert isinstance(pool, list)
        assert all(isinstance(code, str) for code in pool)
