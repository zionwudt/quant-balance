"""Baostock 行情 provider。"""

from __future__ import annotations

from typing import Literal

from quant_balance.data.common import DataLoadError

MarketRow = tuple[str, str, float, float, float, float, float]


def _to_baostock_code(ts_code: str) -> str:
    try:
        code, market = ts_code.split(".")
    except ValueError as exc:
        raise DataLoadError(f"无法识别股票代码格式: {ts_code}") from exc

    market = market.lower()
    if market not in {"sh", "sz"}:
        raise DataLoadError(f"Baostock 暂不支持该市场代码: {ts_code}")
    return f"{market}.{code}"


def _safe_float(value: object) -> float:
    text = str(value).strip()
    if not text:
        return 0.0
    return float(text)


def fetch_daily_bar_rows(
    ts_code: str,
    start_date: str,
    end_date: str,
    adjust: Literal["none", "qfq"],
) -> list[MarketRow]:
    """通过 Baostock 拉取日线行情。"""
    try:
        import baostock as bs
    except ImportError as exc:
        raise DataLoadError(
            "需要安装 baostock 才能获取行情数据，请运行：pip install baostock"
        ) from exc

    adjustflag = {"none": "3", "qfq": "2"}[adjust]
    login_result = bs.login()
    if login_result.error_code != "0":
        raise DataLoadError(f"Baostock 登录失败: {login_result.error_msg}")

    try:
        rs = bs.query_history_k_data_plus(
            _to_baostock_code(ts_code),
            "date,open,high,low,close,volume",
            start_date=f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}",
            end_date=f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}",
            frequency="d",
            adjustflag=adjustflag,
        )
        if rs.error_code != "0":
            raise DataLoadError(f"Baostock 查询失败: {rs.error_msg}")

        rows: list[MarketRow] = []
        while rs.next():
            date, open_, high, low, close, volume = rs.get_row_data()
            rows.append((
                ts_code,
                date.replace("-", ""),
                _safe_float(open_),
                _safe_float(high),
                _safe_float(low),
                _safe_float(close),
                _safe_float(volume),
            ))
        return rows
    finally:
        bs.logout()

