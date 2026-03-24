"""统一的日线行情加载入口。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from quant_balance.data.cb_loader import load_dataframe as load_cb_dataframe
from quant_balance.data.akshare_loader import fetch_daily_bar_rows as fetch_akshare_daily_bar_rows
from quant_balance.data.baostock_loader import fetch_daily_bar_rows as fetch_baostock_daily_bar_rows
from quant_balance.data.common import DataLoadError, resolve_daily_provider_order
from quant_balance.data.market_cache import get_connection, query_daily_bars, save_daily_bars
from quant_balance.data.tushare_loader import load_dataframe as load_tushare_dataframe
from quant_balance.logging_utils import get_logger, log_event

MarketRow = tuple[str, str, float, float, float, float, float]
MarketFetcher = Callable[[str, str, str, Literal["none", "qfq"]], list[MarketRow]]

_PROVIDER_FETCHERS: dict[str, MarketFetcher] = {
    "akshare": fetch_akshare_daily_bar_rows,
    "baostock": fetch_baostock_daily_bar_rows,
}

logger = get_logger(__name__)


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
    df.attrs["asset_type"] = "stock"
    return df


def _resolve_cb_provider_order(
    *,
    provider: str | None = None,
    providers: Sequence[str] | None = None,
) -> list[str]:
    if provider is None and providers is None:
        return ["tushare"]

    provider_order = resolve_daily_provider_order(provider=provider, providers=providers)
    unsupported = [name for name in provider_order if name != "tushare"]
    if unsupported:
        raise DataLoadError("可转债当前仅支持 tushare 日线数据源。")
    return provider_order


def load_dataframe(
    ts_code: str,
    start_date: str,
    end_date: str,
    *,
    asset_type: Literal["stock", "convertible_bond"] = "stock",
    adjust: Literal["none", "qfq"] = "qfq",
    provider: str | None = None,
    providers: Sequence[str] | None = None,
    db_path: Path | None = None,
) -> pd.DataFrame:
    """加载日线行情，支持多数据源按顺序回退。"""
    if asset_type == "convertible_bond":
        _resolve_cb_provider_order(provider=provider, providers=providers)
        df = load_cb_dataframe(ts_code, start_date, end_date, db_path=db_path)
        df.attrs["asset_type"] = "convertible_bond"
        return df
    if asset_type != "stock":
        raise DataLoadError(f"不支持的资产类型 {asset_type!r}，当前支持: stock, convertible_bond")

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
            df.attrs["asset_type"] = "stock"
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
                log_event(
                    logger,
                    "CACHE_HIT",
                    data_provider=provider_name,
                    dataset="daily_bars",
                    symbol=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust,
                    rows_count=len(cached_rows),
                )
                return _rows_to_dataframe(cached_rows, provider=provider_name)

            log_event(
                logger,
                "CACHE_MISS",
                data_provider=provider_name,
                dataset="daily_bars",
                symbol=ts_code,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
            )
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
