"""fundamental_loader 单元测试 —— 公告日对齐与增量缓存。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

import quant_balance.data.fundamental_loader as loader
from quant_balance.data.fundamental_loader import (
    FinancialSnapshot,
    _CREATE_FETCH_LOG_SQL,
    _CREATE_TABLE_SQLS,
    _DATASET_REGISTRY,
    load_financial_at,
    update_fundamental_cache,
)


FINA_INDICATOR_ROWS = [
    ("600519.SH", "20231028", "20230930", 40.5, 200.0, 25.8, 24.1, 19.0, 91.2, 45.3, 1.7, 1.2, 0.28),
    ("600519.SH", "20240420", "20231231", 55.2, 220.0, 28.1, 26.6, 21.7, 92.0, 46.1, 1.8, 1.3, 0.30),
    ("600519.SH", "20240426", "20240331", 12.3, 225.0, 6.5, 6.0, 5.1, 89.8, 44.0, 1.6, 1.1, 0.08),
]

INCOME_ROWS = [
    ("600519.SH", "20231028", "20230930", 10_000_000_000.0, 9_900_000_000.0, 6_000_000_000.0, 6_500_000_000.0, 5_000_000_000.0, 4_900_000_000.0),
    ("600519.SH", "20240420", "20231231", 15_000_000_000.0, 14_900_000_000.0, 8_500_000_000.0, 9_200_000_000.0, 7_500_000_000.0, 7_400_000_000.0),
    ("600519.SH", "20240426", "20240331", 4_000_000_000.0, 3_950_000_000.0, 2_000_000_000.0, 2_200_000_000.0, 1_800_000_000.0, 1_750_000_000.0),
]

BALANCESHEET_ROWS = [
    ("600519.SH", "20231028", "20230930", 12_000_000_000.0, 25_000_000_000.0, 8_000_000_000.0, 17_000_000_000.0, 16_800_000_000.0),
    ("600519.SH", "20240420", "20231231", 13_500_000_000.0, 28_000_000_000.0, 8_500_000_000.0, 19_500_000_000.0, 19_200_000_000.0),
    ("600519.SH", "20240426", "20240331", 14_000_000_000.0, 29_000_000_000.0, 8_800_000_000.0, 20_200_000_000.0, 19_900_000_000.0),
]

CASHFLOW_ROWS = [
    ("600519.SH", "20231028", "20230930", 5_200_000_000.0, -1_000_000_000.0, -500_000_000.0),
    ("600519.SH", "20240420", "20231231", 7_600_000_000.0, -1_200_000_000.0, -800_000_000.0),
    ("600519.SH", "20240426", "20240331", 1_900_000_000.0, -300_000_000.0, -150_000_000.0),
]

DAILY_BASIC_ROWS = [
    ("600519.SH", "20240112", 30.0, 30.5, 8.4, 13.0, 13.4, 1.2, 1.1, 125_619.0, 91_500.0, 80_000.0, 2_580_000.0, 1_880_000.0),
    ("600519.SH", "20240315", 31.2, 31.8, 8.6, 13.4, 13.8, 1.2, 1.1, 125_619.0, 91_500.0, 80_000.0, 2_620_000.0, 1_910_000.0),
    ("600519.SH", "20240420", 32.8, 33.1, 8.9, 13.9, 14.2, 1.2, 1.1, 125_619.0, 91_500.0, 80_000.0, 2_700_000.0, 1_950_000.0),
    ("600519.SH", "20240501", 33.5, 34.0, 9.1, 14.1, 14.5, 1.2, 1.1, 125_619.0, 91_500.0, 80_000.0, 2_760_000.0, 1_980_000.0),
]

DATASET_ROWS = {
    "daily_basic": DAILY_BASIC_ROWS,
    "income": INCOME_ROWS,
    "balancesheet": BALANCESHEET_ROWS,
    "cashflow": CASHFLOW_ROWS,
    "fina_indicator": FINA_INDICATOR_ROWS,
}


def _seed_db(
    db_path: Path,
    *,
    dataset_rows: dict[str, list[tuple]] | None = None,
    fetch_log_rows: list[tuple[str, str, str]] | None = None,
) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        for sql in _CREATE_TABLE_SQLS.values():
            conn.execute(sql)
        conn.execute(_CREATE_FETCH_LOG_SQL)

        for dataset_name, rows in (dataset_rows or {}).items():
            dataset = _DATASET_REGISTRY[dataset_name]
            conn.executemany(dataset.upsert_sql, rows)

        if fetch_log_rows:
            conn.executemany(
                "INSERT INTO fundamental_fetch_log (ts_code, dataset, last_synced_date) VALUES (?, ?, ?)",
                fetch_log_rows,
            )
        conn.commit()
    finally:
        conn.close()


def _full_fetch_log(ts_code: str, *, last_synced_date: str) -> list[tuple[str, str, str]]:
    return [
        (ts_code, dataset_name, last_synced_date)
        for dataset_name in _DATASET_REGISTRY
    ]


def _frame_for_dataset(
    dataset_name: str,
    rows: list[tuple],
    *,
    start_date: str | None,
    end_date: str,
) -> pd.DataFrame:
    dataset = _DATASET_REGISTRY[dataset_name]
    frame = pd.DataFrame(rows, columns=dataset.select_columns)
    if frame.empty:
        return frame
    mask = frame[dataset.date_column] <= end_date
    if start_date is not None:
        mask &= frame[dataset.date_column] >= start_date
    return frame.loc[mask].reset_index(drop=True)


class _FakeTusharePro:
    def __init__(self, dataset_rows: dict[str, list[tuple]]) -> None:
        self.dataset_rows = dataset_rows
        self.calls: list[dict[str, str | None]] = []

    def _fetch(self, dataset_name: str, **kwargs) -> pd.DataFrame:
        self.calls.append(
            {
                "dataset": dataset_name,
                "start_date": kwargs.get("start_date"),
                "end_date": kwargs.get("end_date"),
                "fields": kwargs.get("fields"),
            }
        )
        return _frame_for_dataset(
            dataset_name,
            self.dataset_rows.get(dataset_name, []),
            start_date=kwargs.get("start_date"),
            end_date=kwargs["end_date"],
        )

    def daily_basic(self, **kwargs) -> pd.DataFrame:
        return self._fetch("daily_basic", **kwargs)

    def income(self, **kwargs) -> pd.DataFrame:
        return self._fetch("income", **kwargs)

    def balancesheet(self, **kwargs) -> pd.DataFrame:
        return self._fetch("balancesheet", **kwargs)

    def cashflow(self, **kwargs) -> pd.DataFrame:
        return self._fetch("cashflow", **kwargs)

    def fina_indicator(self, **kwargs) -> pd.DataFrame:
        return self._fetch("fina_indicator", **kwargs)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "cache.db"
    _seed_db(
        path,
        dataset_rows=DATASET_ROWS,
        fetch_log_rows=(
            _full_fetch_log("600519.SH", last_synced_date="20240501")
            + _full_fetch_log("999999.SH", last_synced_date="20240501")
        ),
    )
    return path


class TestLoadFinancialAt:
    def test_jan_query_returns_q3_not_q4(self, db_path: Path) -> None:
        snap = load_financial_at("600519.SH", "2024-01-15", db_path=db_path)
        assert snap is not None
        assert snap.end_date == "20230930"
        assert snap.ann_date == "20231028"

    def test_never_returns_future_announcement(self, db_path: Path) -> None:
        snap = load_financial_at("600519.SH", "2024-03-15", db_path=db_path)
        assert snap is not None
        assert snap.ann_date <= "20240315"
        assert snap.end_date == "20230930"

    def test_returns_q4_after_announcement(self, db_path: Path) -> None:
        snap = load_financial_at("600519.SH", "2024-04-20", db_path=db_path)
        assert snap is not None
        assert snap.end_date == "20231231"
        assert snap.ann_date == "20240420"

    def test_returns_latest_when_multiple_announced(self, db_path: Path) -> None:
        snap = load_financial_at("600519.SH", "2024-05-01", db_path=db_path)
        assert snap is not None
        assert snap.end_date == "20240331"
        assert snap.ann_date == "20240426"

    def test_returns_none_before_any_announcement(self, db_path: Path) -> None:
        snap = load_financial_at("600519.SH", "2023-01-01", db_path=db_path)
        assert snap is None

    def test_returns_none_for_unknown_symbol(self, db_path: Path) -> None:
        snap = load_financial_at("999999.SH", "2024-01-15", db_path=db_path)
        assert snap is None

    def test_announcement_day_boundary(self, db_path: Path) -> None:
        snap = load_financial_at("600519.SH", "2023-10-28", db_path=db_path)
        assert snap is not None
        assert snap.ann_date == "20231028"

    def test_day_before_announcement_excluded(self, db_path: Path) -> None:
        snap = load_financial_at("600519.SH", "2023-10-27", db_path=db_path)
        assert snap is None

    def test_returns_financial_snapshot_type(self, db_path: Path) -> None:
        snap = load_financial_at("600519.SH", "2024-01-15", db_path=db_path)
        assert isinstance(snap, FinancialSnapshot)

    def test_cache_hit_reuses_local_tables_without_fetch(self, db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def _unexpected_fetch() -> object:
            raise AssertionError("cache hit should not create tushare client")

        monkeypatch.setattr(loader, "_create_tushare_client", _unexpected_fetch)
        snap = load_financial_at("600519.SH", "2024-01-15", db_path=db_path)
        assert snap is not None
        assert snap.end_date == "20230930"

    def test_snapshot_includes_valuation_and_statement_fields(self, db_path: Path) -> None:
        snap = load_financial_at("600519.SH", "2024-05-01", db_path=db_path)
        assert snap is not None
        assert snap.trade_date == "20240501"
        assert snap.pe == 33.5
        assert snap.pb == 9.1
        assert snap.net_profit == 1_750_000_000.0
        assert snap.total_assets == 29_000_000_000.0
        assert snap.n_cashflow_act == 1_900_000_000.0


def test_update_fundamental_cache_supports_incremental_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "cache.db"
    pro = _FakeTusharePro(DATASET_ROWS)
    monkeypatch.setattr(loader, "_create_tushare_client", lambda: pro)

    first_counts = update_fundamental_cache("600519.SH", until_date="2024-04-20", db_path=db_path)
    assert first_counts["fina_indicator"] == 2
    first_snap = load_financial_at("600519.SH", "2024-04-20", db_path=db_path)
    assert first_snap is not None
    assert first_snap.end_date == "20231231"
    assert first_snap.trade_date == "20240420"

    second_counts = update_fundamental_cache("600519.SH", until_date="2024-05-01", db_path=db_path)
    assert second_counts["daily_basic"] >= 1
    second_snap = load_financial_at("600519.SH", "2024-05-01", db_path=db_path)
    assert second_snap is not None
    assert second_snap.end_date == "20240331"
    assert second_snap.trade_date == "20240501"
    assert any(
        call["dataset"] == "fina_indicator" and call["start_date"] == "20240420" and call["end_date"] == "20240501"
        for call in pro.calls
    )

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT last_synced_date FROM fundamental_fetch_log WHERE ts_code = ? AND dataset = ?",
            ("600519.SH", "fina_indicator"),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "20240501"


def test_load_financial_at_returns_none_when_remote_has_no_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "cache.db"
    pro = _FakeTusharePro({})
    monkeypatch.setattr(loader, "_create_tushare_client", lambda: pro)

    snap = load_financial_at("300999.SZ", "2024-05-01", db_path=db_path)

    assert snap is None
    assert {call["dataset"] for call in pro.calls} == set(_DATASET_REGISTRY)
