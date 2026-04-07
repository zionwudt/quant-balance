"""多股票数据批量加载适配器。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import pandas as pd

from quant_balance.data import DataLoadError, load_dataframe
from quant_balance.data.common import resolve_daily_provider_order
from quant_balance.logging_utils import get_logger, log_event

logger = get_logger(__name__)
MINUTE_TIMEFRAMES = frozenset({"1min", "5min", "15min", "30min", "60min"})


def load_multi_dataframes(
    symbols: list[str],
    start_date: str,
    end_date: str,
    *,
    asset_type: Literal["stock", "convertible_bond"] = "stock",
    timeframe: Literal["1d", "1min", "5min", "15min", "30min", "60min"] = "1d",
    adjust: Literal["none", "qfq"] = "qfq",
    data_provider: str | None = None,
    db_path: Path | None = None,
) -> dict[str, pd.DataFrame]:
    """批量加载多只股票的 OHLCV DataFrame。

    返回 {symbol: DataFrame} 字典，加载失败的股票会被跳过并打印警告。
    """
    normalized_provider = (
        str(data_provider).strip().lower() if data_provider is not None else None
    )
    if asset_type not in {"stock", "convertible_bond"}:
        raise DataLoadError(
            f"不支持的资产类型 {asset_type!r}，当前支持: stock, convertible_bond"
        )
    if asset_type == "convertible_bond":
        if timeframe != "1d":
            raise DataLoadError("可转债当前仅支持 tushare 日线数据，不支持分钟线。")
        if normalized_provider not in (None, "tushare"):
            raise DataLoadError("可转债当前仅支持 tushare 日线数据源。")
    elif timeframe in MINUTE_TIMEFRAMES and normalized_provider not in (None, "tushare"):
        raise DataLoadError("分钟线当前仅支持 tushare 数据源。")

    if normalized_provider is not None:
        resolve_daily_provider_order(provider=normalized_provider)

    result: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        try:
            load_kwargs = {
                "asset_type": asset_type,
                "timeframe": timeframe,
                "adjust": adjust,
                "db_path": db_path,
            }
            if data_provider is not None:
                load_kwargs["provider"] = data_provider
            df = load_dataframe(symbol, start_date, end_date, **load_kwargs)
            if not df.empty:
                result[symbol] = df
        except DataLoadError as exc:
            log_event(
                logger,
                "DATA_LOAD_SKIP",
                level=logging.WARNING,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                asset_type=asset_type,
                timeframe=timeframe,
                adjust=adjust,
                data_provider=data_provider,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
    return result
