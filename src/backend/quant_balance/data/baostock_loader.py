"""Baostock 行情 provider。"""

from __future__ import annotations

from typing import Literal

from quant_balance.data.common import DataLoadError

MarketRow = tuple[str, str, float, float, float, float, float]

StockListRow = tuple[str, str, str, str | None, str, str]


def fetch_stock_list() -> list[StockListRow]:
    """通过 BaoStock 拉取 A 股股票列表。

    Returns:
        list of (ts_code, name, list_date, delist_date, industry, market)
    """
    try:
        import baostock as bs
    except ImportError as exc:
        raise DataLoadError(
            "需要安装 baostock 才能获取股票列表，请运行：pip install baostock"
        ) from exc

    login_result = bs.login()
    if login_result.error_code != "0":
        raise DataLoadError(f"BaoStock 登录失败: {login_result.error_msg}")

    try:
        # query_all_stock 返回当日可交易股票: code, tradeStatus, code_name
        rs = bs.query_all_stock(day="")
        if rs.error_code != "0":
            raise DataLoadError(f"BaoStock query_all_stock 失败: {rs.error_msg}")

        all_stocks = rs.get_data()
        if all_stocks is None or all_stocks.empty:
            raise DataLoadError("BaoStock 未返回任何股票数据")

        # 获取行业分类
        industry_map: dict[str, str] = {}
        try:
            rs_ind = bs.query_stock_industry()
            if rs_ind.error_code == "0":
                ind_df = rs_ind.get_data()
                if ind_df is not None and not ind_df.empty:
                    for _, row in ind_df.iterrows():
                        bs_code = str(row.get("code", "")).strip()
                        ind = str(row.get("industry", "")).strip()
                        if bs_code and ind:
                            industry_map[bs_code] = ind
        except Exception:  # noqa: BLE001
            pass

        rows: list[StockListRow] = []
        seen: set[str] = set()

        for _, r in all_stocks.iterrows():
            bs_code = str(r.get("code", "")).strip()
            code_name = str(r.get("code_name", "")).strip()

            if not bs_code or "." not in bs_code:
                continue

            parts = bs_code.split(".")
            if len(parts) != 2:
                continue
            market_prefix, stock_code = parts
            market = market_prefix.upper()
            if market not in ("SH", "SZ"):
                continue
            # 过滤非 A 股（指数、B 股等）
            if not stock_code.isdigit() or len(stock_code) != 6:
                continue
            # 简单过滤：A 股代码通常以 0/3/6 开头
            first_digit = stock_code[0]
            if first_digit not in ("0", "3", "6"):
                continue

            ts_code = f"{stock_code}.{market}"
            if ts_code in seen:
                continue
            seen.add(ts_code)

            industry = industry_map.get(bs_code, "")
            market_name = "沪市" if market == "SH" else "深市"
            # BaoStock query_all_stock 不提供 list_date，留空
            rows.append((ts_code, code_name, "", None, industry, market_name))

        if not rows:
            raise DataLoadError("BaoStock 未能获取到任何 A 股股票信息")
        return rows
    finally:
        bs.logout()


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

