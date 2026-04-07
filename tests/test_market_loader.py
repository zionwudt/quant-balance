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


def test_load_dataframe_routes_convertible_bond_to_cb_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, object] = {}

    def fake_cb_loader(ts_code: str, start_date: str, end_date: str, *, db_path: Path | None = None):
        called.update({
            "ts_code": ts_code,
            "start_date": start_date,
            "end_date": end_date,
            "db_path": db_path,
        })
        import pandas as pd

        df = pd.DataFrame(
            {"Open": [100.0], "High": [101.0], "Low": [99.0], "Close": [100.5], "Volume": [1000.0]},
            index=pd.to_datetime(["2026-01-05"]),
        )
        df.attrs["data_provider"] = "tushare"
        df.attrs["asset_type"] = "convertible_bond"
        return df

    monkeypatch.setattr("quant_balance.data.market_loader.load_cb_dataframe", fake_cb_loader)

    df = load_dataframe(
        "110043.SH",
        "2026-01-05",
        "2026-01-06",
        asset_type="convertible_bond",
        db_path=tmp_path / "cache.db",
    )

    assert list(df["Close"]) == [100.5]
    assert df.attrs["asset_type"] == "convertible_bond"
    assert called["ts_code"] == "110043.SH"


def test_load_dataframe_routes_minute_timeframe_to_tushare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, object] = {}

    def fake_tushare_loader(
        ts_code: str,
        start_date: str,
        end_date: str,
        *,
        timeframe: str = "1d",
        adjust: str = "qfq",
        db_path: Path | None = None,
    ):
        called.update({
            "ts_code": ts_code,
            "start_date": start_date,
            "end_date": end_date,
            "timeframe": timeframe,
            "adjust": adjust,
            "db_path": db_path,
        })
        import pandas as pd

        df = pd.DataFrame(
            {"Open": [10.0], "High": [10.2], "Low": [9.9], "Close": [10.1], "Volume": [1000.0]},
            index=pd.to_datetime(["2026-01-05 09:30:00"]),
        )
        df.attrs["data_provider"] = "tushare"
        df.attrs["asset_type"] = "stock"
        df.attrs["timeframe"] = timeframe
        df.attrs["price_adjustment"] = "none"
        return df

    monkeypatch.setattr("quant_balance.data.market_loader.load_tushare_dataframe", fake_tushare_loader)

    df = load_dataframe(
        "600519.SH",
        "2026-01-05 09:30:00",
        "2026-01-05 15:00:00",
        timeframe="1min",
        provider="tushare",
        db_path=tmp_path / "cache.db",
    )

    assert list(df["Close"]) == [10.1]
    assert df.attrs["timeframe"] == "1min"
    assert df.attrs["price_adjustment"] == "none"
    assert called["timeframe"] == "1min"


def test_load_dataframe_routes_minute_timeframe_to_tushare_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, object] = {}

    def fake_tushare_loader(
        ts_code: str,
        start_date: str,
        end_date: str,
        *,
        timeframe: str = "1d",
        adjust: str = "qfq",
        db_path: Path | None = None,
    ):
        called.update({
            "ts_code": ts_code,
            "start_date": start_date,
            "end_date": end_date,
            "timeframe": timeframe,
            "adjust": adjust,
            "db_path": db_path,
        })
        import pandas as pd

        df = pd.DataFrame(
            {"Open": [10.0], "High": [10.2], "Low": [9.9], "Close": [10.1], "Volume": [1000.0]},
            index=pd.to_datetime(["2026-01-05 09:30:00"]),
        )
        df.attrs["data_provider"] = "tushare"
        df.attrs["asset_type"] = "stock"
        df.attrs["timeframe"] = timeframe
        df.attrs["price_adjustment"] = "none"
        return df

    monkeypatch.setattr("quant_balance.data.market_loader.load_tushare_dataframe", fake_tushare_loader)

    df = load_dataframe(
        "600519.SH",
        "2026-01-05 09:30:00",
        "2026-01-05 15:00:00",
        timeframe="1min",
        db_path=tmp_path / "cache.db",
    )

    assert list(df["Close"]) == [10.1]
    assert df.attrs["data_provider"] == "tushare"
    assert called["start_date"] == "2026-01-05 09:30:00"
    assert called["end_date"] == "2026-01-05 15:00:00"


def test_load_dataframe_rejects_non_tushare_provider_for_convertible_bond(tmp_path: Path) -> None:
    with pytest.raises(DataLoadError, match="仅支持 tushare"):
        load_dataframe(
            "110043.SH",
            "2026-01-05",
            "2026-01-06",
            asset_type="convertible_bond",
            provider="akshare",
            db_path=tmp_path / "cache.db",
        )


def test_load_dataframe_rejects_minute_timeframe_for_convertible_bond(tmp_path: Path) -> None:
    with pytest.raises(DataLoadError, match="不支持分钟线"):
        load_dataframe(
            "110043.SH",
            "2026-01-05 09:30:00",
            "2026-01-05 15:00:00",
            asset_type="convertible_bond",
            timeframe="1min",
            db_path=tmp_path / "cache.db",
        )


def test_load_dataframe_rejects_minute_timeframe_for_non_tushare_provider(tmp_path: Path) -> None:
    with pytest.raises(DataLoadError, match="分钟线当前仅支持 tushare"):
        load_dataframe(
            "AAA",
            "2026-01-05 09:30:00",
            "2026-01-05 15:00:00",
            timeframe="1min",
            provider="akshare",
            db_path=tmp_path / "cache.db",
        )
