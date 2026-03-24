from __future__ import annotations

from pathlib import Path

import pytest

from quant_balance.data.common import DataLoadError
from quant_balance.data.market_cache import get_connection, save_daily_bars
from quant_balance.data.market_loader import _PROVIDER_FETCHERS, load_dataframe


def _seed_provider_cache(db_path: Path, *, provider: str, adjust: str, rows: list[tuple]) -> None:
    conn = get_connection(db_path)
    try:
        save_daily_bars(conn, provider=provider, adjust=adjust, rows=rows)
    finally:
        conn.close()


def test_load_dataframe_can_read_provider_cache(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    _seed_provider_cache(
        db_path,
        provider="akshare",
        adjust="qfq",
        rows=[
            ("AAA", "20260105", 10.0, 10.5, 9.8, 10.2, 1_000.0),
            ("AAA", "20260106", 10.1, 10.6, 9.9, 10.3, 1_100.0),
        ],
    )

    df = load_dataframe("AAA", "2026-01-05", "2026-01-06", provider="akshare", db_path=db_path)

    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert list(df["Close"]) == [10.2, 10.3]
    assert df.attrs["data_provider"] == "akshare"


def test_load_dataframe_falls_back_to_next_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "cache.db"

    def fail_fetcher(ts_code: str, start_date: str, end_date: str, adjust: str) -> list[tuple]:
        raise DataLoadError("provider unavailable")

    def ok_fetcher(ts_code: str, start_date: str, end_date: str, adjust: str) -> list[tuple]:
        assert (ts_code, start_date, end_date, adjust) == ("AAA", "20260105", "20260106", "qfq")
        return [
            ("AAA", "20260105", 10.0, 10.0, 9.8, 9.9, 1_000.0),
            ("AAA", "20260106", 10.1, 10.3, 10.0, 10.2, 1_050.0),
        ]

    monkeypatch.setitem(_PROVIDER_FETCHERS, "akshare", fail_fetcher)
    monkeypatch.setitem(_PROVIDER_FETCHERS, "baostock", ok_fetcher)

    df = load_dataframe(
        "AAA",
        "2026-01-05",
        "2026-01-06",
        providers=["akshare", "baostock"],
        db_path=db_path,
    )

    assert list(df["Close"]) == [9.9, 10.2]
    assert df.attrs["data_provider"] == "baostock"

    cached = load_dataframe("AAA", "2026-01-05", "2026-01-06", provider="baostock", db_path=db_path)
    assert list(cached["Close"]) == [9.9, 10.2]


def test_load_dataframe_rejects_unknown_provider(tmp_path: Path) -> None:
    with pytest.raises(DataLoadError, match="不支持的数据源"):
        load_dataframe("AAA", "2026-01-05", "2026-01-06", provider="unknown", db_path=tmp_path / "cache.db")

