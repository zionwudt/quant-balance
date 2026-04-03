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
        # query_stock_industry 返回全量股票及行业分类（不依赖交易日）
        # 列: updateDate, code, code_name, industry, industryClassification
        industry_map: dict[str, tuple[str, str]] = {}
        try:
            rs_ind = bs.query_stock_industry()
            if rs_ind.error_code == "0":
                ind_df = rs_ind.get_data()
                if ind_df is not None and not ind_df.empty:
                    for _, row in ind_df.iterrows():
                        bs_code = str(row.get("code", "")).strip()
                        code_name = str(row.get("code_name", "")).strip()
                        ind = str(row.get("industry", "")).strip()
                        if bs_code:
                            industry_map[bs_code] = (code_name, ind)
        except Exception:  # noqa: BLE001
            pass

        # 如果 industry 数据充足，直接用作股票列表来源
        rows: list[StockListRow] = []
        seen: set[str] = set()

        if industry_map:
            for bs_code, (code_name, industry) in industry_map.items():
                ts_code = _bs_code_to_ts_code(bs_code)
                if ts_code is None or ts_code in seen:
                    continue
                seen.add(ts_code)
                market_name = "沪市" if ts_code.endswith(".SH") else "深市"
                rows.append((ts_code, code_name, "", None, industry, market_name))

        # 如果行业数据不足，用 query_all_stock 补充（需要有效交易日）
        if len(rows) < 1000:
            _supplement_from_all_stock(bs, rows, seen)

        if not rows:
            raise DataLoadError("BaoStock 未能获取到任何 A 股股票信息")
        return rows
    finally:
        bs.logout()


def _bs_code_to_ts_code(bs_code: str) -> str | None:
    """将 BaoStock 代码 (sh.600000) 转为 Tushare 格式 (600000.SH)。"""
    if "." not in bs_code:
        return None
    parts = bs_code.split(".")
    if len(parts) != 2:
        return None
    market_prefix, stock_code = parts
    market = market_prefix.upper()
    if market not in ("SH", "SZ"):
        return None
    if not stock_code.isdigit() or len(stock_code) != 6:
        return None
    # A 股代码以 0/3/6 开头
    if stock_code[0] not in ("0", "3", "6"):
        return None
    return f"{stock_code}.{market}"


def _supplement_from_all_stock(
    bs_module: object,
    rows: list[StockListRow],
    seen: set[str],
) -> None:
    """用 query_all_stock 补充遗漏的股票。"""
    from datetime import date, timedelta

    # 尝试最近 7 个日期（跳过周末/节假日）
    today = date.today()
    for delta in range(0, 7):
        day = today - timedelta(days=delta)
        day_str = day.strftime("%Y-%m-%d")
        try:
            rs = bs_module.query_all_stock(day=day_str)
            if rs.error_code != "0":
                continue
            df = rs.get_data()
            if df is None or df.empty:
                continue
            for _, r in df.iterrows():
                bs_code = str(r.get("code", "")).strip()
                code_name = str(r.get("code_name", "")).strip()
                ts_code = _bs_code_to_ts_code(bs_code)
                if ts_code is None or ts_code in seen:
                    continue
                seen.add(ts_code)
                market_name = "沪市" if ts_code.endswith(".SH") else "深市"
                rows.append((ts_code, code_name, "", None, "", market_name))
            break  # 成功获取即退出
        except Exception:  # noqa: BLE001
            continue


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

