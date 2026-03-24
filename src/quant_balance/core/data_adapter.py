"""多股票数据批量加载适配器。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pandas as pd

from quant_balance.data.tushare_loader import load_dataframe


def load_multi_dataframes(
    symbols: list[str],
    start_date: str,
    end_date: str,
    *,
    adjust: Literal["none", "qfq"] = "qfq",
    db_path: Path | None = None,
) -> dict[str, pd.DataFrame]:
    """批量加载多只股票的 OHLCV DataFrame。

    返回 {symbol: DataFrame} 字典，加载失败的股票会被跳过并打印警告。
    """
    result: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        try:
            df = load_dataframe(
                symbol, start_date, end_date,
                adjust=adjust, db_path=db_path,
            )
            if not df.empty:
                result[symbol] = df
        except Exception as exc:  # noqa: BLE001
            print(f"[data_adapter] 跳过 {symbol}: {exc}")
    return result
