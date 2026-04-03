"""stock_pool 单元测试 —— 历史池与过滤器。"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

import quant_balance.data.stock_pool as stock_pool
from quant_balance.data.common import DataLoadError
from quant_balance.data.fundamental_loader import FinancialSnapshot
from quant_balance.data.stock_pool import (
    StockPoolRecord,
    _CREATE_STOCK_LIST_SQL,
    _CREATE_NAME_CHANGE_FETCH_LOG_SQL,
    _CREATE_NAME_CHANGE_SQL,
    _CREATE_STOCK_LIST_FETCH_LOG_SQL,
    filter_pool_at_date,
    get_pool_at_date,
    search_stock_candidates,
)


def _seed_db(
    db_path: Path,
    rows: list[tuple],
    *,
    name_changes: list[tuple] | None = None,
    fetched_name_change_symbols: list[str] | None = None,
) -> None:
    """向测试数据库插入股票池与更名缓存。"""
    conn = sqlite3.connect(str(db_path))
    conn.execute(_CREATE_STOCK_LIST_SQL)
    conn.execute(_CREATE_NAME_CHANGE_SQL)
    conn.execute(_CREATE_NAME_CHANGE_FETCH_LOG_SQL)
    conn.execute(_CREATE_STOCK_LIST_FETCH_LOG_SQL)
    conn.executemany(
        "INSERT INTO stock_list (ts_code, name, list_date, delist_date, industry, market) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    # 设置 fetch 时间戳，防止测试中触发远程数据源刷新
    from datetime import datetime
    conn.execute(
        "INSERT OR REPLACE INTO stock_list_fetch_log (id, last_fetched_at) VALUES (1, ?)",
        (datetime.now().isoformat(timespec="seconds"),),
    )
    if name_changes:
        conn.executemany(
            "INSERT INTO stock_name_changes (ts_code, name, start_date, end_date) VALUES (?, ?, ?, ?)",
            name_changes,
        )
    if fetched_name_change_symbols:
        conn.executemany(
            "INSERT INTO stock_name_change_fetch_log (ts_code) VALUES (?)",
            [(symbol,) for symbol in fetched_name_change_symbols],
        )
    conn.commit()
    conn.close()


# ── 测试数据 ──────────────────────────────────────────────

STOCKS = [
    # ts_code, name, list_date, delist_date, industry, market
    ("000001.SZ", "平安银行", "19910403", None, "银行", "主板"),
    ("600519.SH", "贵州茅台", "20010827", None, "白酒", "主板"),
    ("300999.SZ", "金龙鱼",   "20201015", None, "食品", "创业板"),  # 2020 年上市
    ("000033.SZ", "退市新都", "19970618", "20170712", "房地产", "主板"),  # 曾是 ST
    ("600432.SH", "退市吉恩", "20040120", "20180711", "有色金属", "主板"),  # 已退市
    ("688001.SH", "华兴源创", "20190722", None, "电子", "科创板"),  # 2019 年上市
]

NAME_CHANGES = [
    ("000033.SZ", "*ST新都", "20160509", "20170712"),
]


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test_cache.db"
    _seed_db(
        p,
        STOCKS,
        name_changes=NAME_CHANGES,
        fetched_name_change_symbols=["000033.SZ"],
    )
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


class TestFilterPoolAtDate:
    def test_industry_filter(self, db_path: Path) -> None:
        records = filter_pool_at_date(
            "2015-01-01",
            filters={"industries": ["银行", "白酒"]},
            db_path=db_path,
        )

        assert [record.ts_code for record in records] == ["000001.SZ", "600519.SH"]
        assert all(isinstance(record, StockPoolRecord) for record in records)

    def test_exclude_new_listing_by_min_listing_days(self, db_path: Path) -> None:
        records = filter_pool_at_date(
            "2020-12-31",
            filters={"min_listing_days": 180},
            db_path=db_path,
        )

        assert "300999.SZ" not in [record.ts_code for record in records]

    def test_exclude_st_uses_name_change_history(self, db_path: Path) -> None:
        records = filter_pool_at_date(
            "2017-07-11",
            filters={"exclude_st": True},
            db_path=db_path,
        )

        assert "000033.SZ" not in [record.ts_code for record in records]

    def test_market_cap_and_pe_filters_use_financial_snapshot(
        self,
        db_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        snapshots = {
            "000001.SZ": FinancialSnapshot("000001.SZ", "20240101", "20231231", pe=5.0, total_mv=1_500_000.0),
            "600519.SH": FinancialSnapshot("600519.SH", "20240101", "20231231", pe=28.0, total_mv=2_600_000.0),
            "300999.SZ": FinancialSnapshot("300999.SZ", "20240101", "20231231", pe=35.0, total_mv=800_000.0),
            "688001.SH": FinancialSnapshot("688001.SH", "20240101", "20231231", pe=None, total_mv=None),
            "000033.SZ": FinancialSnapshot("000033.SZ", "20240101", "20231231", pe=12.0, total_mv=300_000.0),
            "600432.SH": FinancialSnapshot("600432.SH", "20240101", "20231231", pe=18.0, total_mv=400_000.0),
        }

        def fake_load_financial_at(symbol: str, as_of_date: str, *, db_path=None):
            return snapshots.get(symbol)

        monkeypatch.setattr(
            "quant_balance.data.fundamental_loader.load_financial_at",
            fake_load_financial_at,
        )

        records = filter_pool_at_date(
            "2024-01-15",
            filters={
                "min_market_cap": 1_000_000.0,
                "max_market_cap": 3_000_000.0,
                "min_pe": 10.0,
                "max_pe": 30.0,
            },
            db_path=db_path,
        )

        assert [record.ts_code for record in records] == ["600519.SH"]
        assert records[0].pe == 28.0
        assert records[0].total_mv == 2_600_000.0

    def test_filter_can_intersect_user_symbols_with_historical_pool(self, db_path: Path) -> None:
        records = filter_pool_at_date(
            "2015-01-01",
            symbols=["300999.SZ", "600519.SH"],
            db_path=db_path,
        )

        assert [record.ts_code for record in records] == ["600519.SH"]

    def test_invalid_filter_range_raises_value_error(self, db_path: Path) -> None:
        with pytest.raises(ValueError, match="min_pe 不能大于 max_pe"):
            filter_pool_at_date(
                "2024-01-15",
                filters={"min_pe": 20.0, "max_pe": 10.0},
                db_path=db_path,
            )


class TestSearchStockCandidates:
    def test_matches_code_and_name(self, db_path: Path) -> None:
        code_matches = search_stock_candidates("600519", db_path=db_path)
        name_matches = search_stock_candidates("平安", db_path=db_path)

        assert code_matches[0]["symbol"] == "600519.SH"
        assert code_matches[0]["name"] == "贵州茅台"
        assert name_matches[0]["symbol"] == "000001.SZ"
        assert name_matches[0]["name"] == "平安银行"

    def test_returns_empty_when_query_blank(self, db_path: Path) -> None:
        assert search_stock_candidates("", db_path=db_path) == []

    def test_raises_data_load_error_when_stock_list_fetch_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        db_path = tmp_path / "empty_cache.db"

        class FakePro:
            def stock_basic(self, **kwargs):
                raise Exception("bad token")

        monkeypatch.setattr(stock_pool, "load_tushare_token", lambda: "token")
        monkeypatch.setitem(
            sys.modules,
            "tushare",
            type("FakeTushare", (), {"pro_api": staticmethod(lambda token: FakePro())})(),
        )

        with pytest.raises(DataLoadError, match="获取股票列表失败"):
            search_stock_candidates("600519", db_path=db_path)
