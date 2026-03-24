"""统一的日线行情加载入口。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from quant_balance.data.akshare_loader import fetch_daily_bar_rows as fetch_akshare_daily_bar_rows
from quant_balance.data.baostock_loader import fetch_daily_bar_rows as fetch_baostock_daily_bar_rows
from quant_balance.data.common import DataLoadError, resolve_daily_provider_order
from quant_balance.data.market_cache import get_connection, query_daily_bars, save_daily_bars
from quant_balance.data.tushare_loader import load_dataframe as load_tushare_dataframe

MarketRow = tuple[str, str, float, float, float, float, float]
MarketFetcher = Callable[[str, str, str, Literal["none", "qfq"]], list[MarketRow]]

_PROVIDER_FETCHERS: dict[str, MarketFetcher] = {
    "akshare": fetch_akshare_daily_bar_rows,
    "baostock": fetch_baostock_daily_bar_rows,
}


def _to_yyyymmdd(iso_date: str) -> str:
    return iso_date.replace("-", "")


def _rows_to_dataframe(rows: list[tuple], *, provider: str) -> pd.DataFrame:
    records = []
    for row in rows:
        records.append({
            "Date": datetime.strptime(row[1], "%Y%m%d"),
            "Open": row[2],
            "High": row[3],
            "Low": row[4],
            "Close": row[5],
            "Volume": row[6],
        })

    df = pd.DataFrame(records)
    df.set_index("Date", inplace=True)
    df.attrs["data_provider"] = provider
    return df


def load_dataframe(
    ts_code: str,
    start_date: str,
    end_date: str,
    *,
    adjust: Literal["none", "qfq"] = "qfq",
    provider: str | None = None,
    providers: Sequence[str] | None = None,
    db_path: Path | None = None,
) -> pd.DataFrame:
    """加载日线行情，支持多数据源按顺序回退。"""
    provider_order = resolve_daily_provider_order(provider=provider, providers=providers)
    start = _to_yyyymmdd(start_date)
    end = _to_yyyymmdd(end_date)

    errors: list[str] = []
    for provider_name in provider_order:
        if provider_name == "tushare":
            try:
                df = load_tushare_dataframe(
                    ts_code,
                    start_date,
                    end_date,
                    adjust=adjust,
                    db_path=db_path,
                )
            except DataLoadError as exc:
                errors.append(f"{provider_name}: {exc}")
                continue
            df.attrs["data_provider"] = provider_name
            return df

        conn = get_connection(db_path)
        try:
            cached_rows = query_daily_bars(
                conn,
                provider=provider_name,
                ts_code=ts_code,
                start_date=start,
                end_date=end,
                adjust=adjust,
            )
            if cached_rows:
                return _rows_to_dataframe(cached_rows, provider=provider_name)

            fetcher = _PROVIDER_FETCHERS[provider_name]
            fresh_rows = fetcher(ts_code, start, end, adjust)
            if not fresh_rows:
                continue

            save_daily_bars(
                conn,
                provider=provider_name,
                adjust=adjust,
                rows=fresh_rows,
            )
            return _rows_to_dataframe(fresh_rows, provider=provider_name)
        except DataLoadError as exc:
            errors.append(f"{provider_name}: {exc}")
        finally:
            conn.close()

    base_message = (
        f"在 {start_date} ~ {end_date} 期间未找到 {ts_code} 的行情数据，"
        "请检查股票代码、日期范围和数据源配置。"
    )
    if errors:
        raise DataLoadError(f"{base_message} 已尝试: {' | '.join(errors)}")
    raise DataLoadError(base_message)

