"""多股票数据批量加载适配器。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import pandas as pd

from quant_balance.data import load_dataframe
from quant_balance.logging_utils import get_logger, log_event

logger = get_logger(__name__)


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
        except Exception as exc:  # noqa: BLE001
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
