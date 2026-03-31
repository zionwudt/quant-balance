"""AkShare 行情 provider。"""

from __future__ import annotations

from typing import Literal

import pandas as pd

from quant_balance.data.common import DataLoadError

MarketRow = tuple[str, str, float, float, float, float, float]


def _to_akshare_symbol(ts_code: str) -> str:
    try:
        code, _market = ts_code.split(".")
    except ValueError as exc:
        raise DataLoadError(f"无法识别股票代码格式: {ts_code}") from exc
    return code


def _pick_column(df: pd.DataFrame, *candidates: str) -> str:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    raise DataLoadError(f"AkShare 返回字段缺失，期望列之一: {candidates}")


def fetch_daily_bar_rows(
    ts_code: str,
    start_date: str,
    end_date: str,
    adjust: Literal["none", "qfq"],
) -> list[MarketRow]:
    """通过 AkShare 拉取日线行情。"""
    try:
        import akshare as ak
    except ImportError as exc:
        raise DataLoadError(
            "需要安装 akshare 才能获取行情数据，请运行：pip install akshare"
        ) from exc

    adjust_param = "" if adjust == "none" else "qfq"
    df = ak.stock_zh_a_hist(
        symbol=_to_akshare_symbol(ts_code),
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust=adjust_param,
    )
    if df is None or df.empty:
        return []

    date_col = _pick_column(df, "日期", "date")
    open_col = _pick_column(df, "开盘", "open")
    high_col = _pick_column(df, "最高", "high")
    low_col = _pick_column(df, "最低", "low")
    close_col = _pick_column(df, "收盘", "close")
    volume_col = _pick_column(df, "成交量", "volume")

    rows: list[MarketRow] = []
    for _, row in df.iterrows():
        trade_date = str(row[date_col]).replace("-", "")
        rows.append((
            ts_code,
            trade_date,
            float(row[open_col]),
            float(row[high_col]),
            float(row[low_col]),
            float(row[close_col]),
            float(row[volume_col]),
        ))
    return rows


def fetch_minute_bar_dataframe(
    ts_code: str,
    start_date: str,
    end_date: str,
    period: str = "5",
    adjust: Literal["none", "qfq"] = "qfq",
) -> pd.DataFrame:
    """通过 AkShare 拉取分钟线行情。

    参数:
        period: "1", "5", "15", "30", "60"
    """
    try:
        import akshare as ak
    except ImportError as exc:
        raise DataLoadError(
            "需要安装 akshare 才能获取分钟线数据，请运行：pip install akshare"
        ) from exc

    adjust_param = "" if adjust == "none" else "qfq"
    try:
        df = ak.stock_zh_a_hist_min_em(
            symbol=_to_akshare_symbol(ts_code),
            period=period,
            start_date=f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]} 09:30:00"
            if len(start_date) == 8
            else start_date,
            end_date=f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]} 15:00:00"
            if len(end_date) == 8
            else end_date,
            adjust=adjust_param,
        )
    except Exception as exc:
        raise DataLoadError(f"AkShare 分钟线加载失败: {exc}") from exc

    if df is None or df.empty:
        return pd.DataFrame()

    date_col = _pick_column(df, "时间", "datetime", "date")
    open_col = _pick_column(df, "开盘", "open")
    high_col = _pick_column(df, "最高", "high")
    low_col = _pick_column(df, "最低", "low")
    close_col = _pick_column(df, "收盘", "close")
    volume_col = _pick_column(df, "成交量", "volume")

    result = pd.DataFrame({
        "Date": pd.to_datetime(df[date_col]),
        "Open": df[open_col].astype(float),
        "High": df[high_col].astype(float),
        "Low": df[low_col].astype(float),
        "Close": df[close_col].astype(float),
        "Volume": df[volume_col].astype(float),
    })
    result.set_index("Date", inplace=True)
    result.attrs["data_provider"] = "akshare"
    result.attrs["asset_type"] = "stock"
    return result

