"""财务数据加载 —— 按公告日对齐，防止未来函数。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
import sqlite3
from pathlib import Path

from quant_balance.data.common import CACHE_DB_PATH, DataLoadError, load_tushare_token
from quant_balance.logging_utils import get_logger, log_event


@dataclass(frozen=True, slots=True)
class _FundamentalDataset:
    """单张基本面缓存表定义。"""

    name: str
    table_name: str
    date_column: str
    value_columns: tuple[str, ...]
    ann_aligned: bool = True

    @property
    def select_columns(self) -> tuple[str, ...]:
        columns = ["ts_code", self.date_column]
        if self.ann_aligned:
            columns.append("end_date")
        columns.extend(self.value_columns)
        return tuple(columns)

    @property
    def request_fields(self) -> str:
        return ",".join(self.select_columns)

    @property
    def upsert_sql(self) -> str:
        placeholders = ", ".join(["?"] * len(self.select_columns))
        columns = ", ".join(self.select_columns)
        return (
            f"INSERT OR REPLACE INTO {self.table_name} "
            f"({columns}) VALUES ({placeholders})"
        )


_DATASET_DEFINITIONS: tuple[_FundamentalDataset, ...] = (
    _FundamentalDataset(
        name="daily_basic",
        table_name="fundamental_daily_basic",
        date_column="trade_date",
        ann_aligned=False,
        value_columns=(
            "pe",
            "pe_ttm",
            "pb",
            "ps",
            "ps_ttm",
            "dv_ratio",
            "dv_ttm",
            "total_share",
            "float_share",
            "free_share",
            "total_mv",
            "circ_mv",
        ),
    ),
    _FundamentalDataset(
        name="income",
        table_name="fundamental_income",
        date_column="ann_date",
        value_columns=(
            "total_revenue",
            "revenue",
            "operate_profit",
            "total_profit",
            "n_income",
            "n_income_attr_p",
        ),
    ),
    _FundamentalDataset(
        name="balancesheet",
        table_name="fundamental_balancesheet",
        date_column="ann_date",
        value_columns=(
            "money_cap",
            "total_assets",
            "total_liab",
            "total_hldr_eqy_exc_min_int",
            "total_hldr_eqy_inc_min_int",
        ),
    ),
    _FundamentalDataset(
        name="cashflow",
        table_name="fundamental_cashflow",
        date_column="ann_date",
        value_columns=(
            "n_cashflow_act",
            "n_cashflow_inv_act",
            "n_cash_flows_fnc_act",
        ),
    ),
    _FundamentalDataset(
        name="fina_indicator",
        table_name="fundamental_fina_indicator",
        date_column="ann_date",
        value_columns=(
            "eps",
            "bps",
            "roe",
            "roe_dt",
            "roa",
            "grossprofit_margin",
            "netprofit_margin",
            "current_ratio",
            "quick_ratio",
            "assets_turn",
        ),
    ),
)

_DATASET_REGISTRY = {dataset.name: dataset for dataset in _DATASET_DEFINITIONS}


def _build_create_table_sql(dataset: _FundamentalDataset) -> str:
    columns = [
        "ts_code TEXT NOT NULL",
        f"{dataset.date_column} TEXT NOT NULL",
    ]
    if dataset.ann_aligned:
        columns.append("end_date TEXT NOT NULL")
    columns.extend(f"{column} REAL" for column in dataset.value_columns)

    if dataset.ann_aligned:
        primary_key = f"PRIMARY KEY (ts_code, {dataset.date_column}, end_date)"
    else:
        primary_key = f"PRIMARY KEY (ts_code, {dataset.date_column})"
    columns.append(primary_key)

    return (
        f"CREATE TABLE IF NOT EXISTS {dataset.table_name} (\n    "
        + ",\n    ".join(columns)
        + "\n);"
    )


_CREATE_TABLE_SQLS = {
    dataset.name: _build_create_table_sql(dataset)
    for dataset in _DATASET_DEFINITIONS
}
_CREATE_FINANCIAL_SQL = _CREATE_TABLE_SQLS["fina_indicator"]
_CREATE_FETCH_LOG_SQL = """
CREATE TABLE IF NOT EXISTS fundamental_fetch_log (
    ts_code TEXT NOT NULL,
    dataset TEXT NOT NULL,
    last_synced_date TEXT NOT NULL,
    PRIMARY KEY (ts_code, dataset)
);
"""

logger = get_logger(__name__)


@dataclass(slots=True)
class FinancialSnapshot:
    """截至某日期的结构化基本面快照。"""

    ts_code: str
    ann_date: str       # 最近财务公告日 YYYYMMDD
    end_date: str       # 最近报告期末 YYYYMMDD
    trade_date: str | None = None  # daily_basic 生效日 YYYYMMDD
    eps: float | None = None
    bps: float | None = None
    roe: float | None = None
    roe_dt: float | None = None
    roa: float | None = None
    grossprofit_margin: float | None = None
    netprofit_margin: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    assets_turn: float | None = None
    total_revenue: float | None = None
    revenue: float | None = None
    operate_profit: float | None = None
    total_profit: float | None = None
    net_profit: float | None = None
    total_assets: float | None = None
    total_liab: float | None = None
    equity: float | None = None
    money_cap: float | None = None
    n_cashflow_act: float | None = None
    n_cashflow_inv_act: float | None = None
    n_cashflow_fnc_act: float | None = None
    pe: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    ps: float | None = None
    ps_ttm: float | None = None
    dv_ratio: float | None = None
    dv_ttm: float | None = None
    total_share: float | None = None
    float_share: float | None = None
    free_share: float | None = None
    total_mv: float | None = None
    circ_mv: float | None = None


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or CACHE_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    for sql in _CREATE_TABLE_SQLS.values():
        conn.execute(sql)
    conn.execute(_CREATE_FETCH_LOG_SQL)
    return conn


def _normalize_date(value: object) -> str | None:
    if value is None:
        return None
    item = getattr(value, "item", None)
    if callable(item):
        try:
            value = item()
        except (TypeError, ValueError):
            pass

    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return None
    return text.split(".")[0].replace("-", "")


def _to_optional_float(value: object) -> float | None:
    if value is None:
        return None

    item = getattr(value, "item", None)
    if callable(item):
        try:
            value = item()
        except (TypeError, ValueError):
            pass

    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"nan", "none", "nat"}:
            return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _coalesce(*values: object) -> float | None:
    for value in values:
        number = _to_optional_float(value)
        if number is not None:
            return number
    return None


def _today_yyyymmdd() -> str:
    return date.today().strftime("%Y%m%d")


def _normalize_until_date(until_date: str | None) -> str:
    if until_date is None:
        return _today_yyyymmdd()
    return until_date.replace("-", "")


def _get_last_synced_date(
    conn: sqlite3.Connection,
    *,
    ts_code: str,
    dataset: str,
) -> str | None:
    row = conn.execute(
        "SELECT last_synced_date FROM fundamental_fetch_log "
        "WHERE ts_code = ? AND dataset = ?",
        (ts_code, dataset),
    ).fetchone()
    if row is None:
        return None
    return str(row["last_synced_date"])


def _set_last_synced_date(
    conn: sqlite3.Connection,
    *,
    ts_code: str,
    dataset: str,
    last_synced_date: str,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO fundamental_fetch_log "
        "(ts_code, dataset, last_synced_date) VALUES (?, ?, ?)",
        (ts_code, dataset, last_synced_date),
    )


def _create_tushare_client() -> object:
    try:
        import tushare as ts
    except ImportError as exc:
        raise DataLoadError(
            "需要安装 tushare 才能获取财务数据，请运行：pip install tushare"
        ) from exc

    token = load_tushare_token()
    return ts.pro_api(token)


def _fetch_dataset_rows(
    pro: object,
    dataset: _FundamentalDataset,
    *,
    ts_code: str,
    start_date: str | None,
    end_date: str,
) -> list[tuple]:
    fetcher = getattr(pro, dataset.name)
    params = {
        "ts_code": ts_code,
        "fields": dataset.request_fields,
        "end_date": end_date,
    }
    if start_date is not None:
        params["start_date"] = start_date

    df = fetcher(**params)
    if df is None or df.empty:
        return []

    rows: list[tuple] = []
    for _, record in df.iterrows():
        date_value = _normalize_date(record.get(dataset.date_column))
        if date_value is None:
            continue

        row: list[object] = [str(record.get("ts_code", ts_code)), date_value]
        if dataset.ann_aligned:
            end_value = _normalize_date(record.get("end_date"))
            if end_value is None:
                continue
            row.append(end_value)

        row.extend(_to_optional_float(record.get(column)) for column in dataset.value_columns)
        rows.append(tuple(row))
    return rows


def _save_dataset_rows(
    conn: sqlite3.Connection,
    dataset: _FundamentalDataset,
    rows: list[tuple],
) -> int:
    if not rows:
        return 0
    conn.executemany(dataset.upsert_sql, rows)
    return len(rows)


def _sync_dataset(
    conn: sqlite3.Connection,
    pro: object,
    dataset: _FundamentalDataset,
    *,
    ts_code: str,
    until_date: str,
) -> int:
    last_synced_date = _get_last_synced_date(conn, ts_code=ts_code, dataset=dataset.name)
    if last_synced_date is not None and last_synced_date >= until_date:
        log_event(
            logger,
            "CACHE_HIT",
            data_provider="tushare",
            dataset=dataset.name,
            symbol=ts_code,
            end_date=until_date,
        )
        return 0

    log_event(
        logger,
        "CACHE_MISS",
        data_provider="tushare",
        dataset=dataset.name,
        symbol=ts_code,
        start_date=last_synced_date,
        end_date=until_date,
    )
    rows = _fetch_dataset_rows(
        pro,
        dataset,
        ts_code=ts_code,
        start_date=last_synced_date,
        end_date=until_date,
    )
    inserted = _save_dataset_rows(conn, dataset, rows)
    _set_last_synced_date(
        conn,
        ts_code=ts_code,
        dataset=dataset.name,
        last_synced_date=until_date,
    )
    return inserted


def _has_any_cached_rows(conn: sqlite3.Connection, ts_code: str) -> bool:
    for dataset in _DATASET_DEFINITIONS:
        row = conn.execute(
            f"SELECT 1 FROM {dataset.table_name} WHERE ts_code = ? LIMIT 1",
            (ts_code,),
        ).fetchone()
        if row is not None:
            return True
    return False


def _query_latest_row(
    conn: sqlite3.Connection,
    dataset: _FundamentalDataset,
    *,
    ts_code: str,
    as_of_date: str,
) -> sqlite3.Row | None:
    columns = ", ".join(dataset.select_columns)
    order_by = f"{dataset.date_column} DESC"
    if dataset.ann_aligned:
        order_by = f"{order_by}, end_date DESC"
    row = conn.execute(
        f"SELECT {columns} FROM {dataset.table_name} "
        f"WHERE ts_code = ? AND {dataset.date_column} <= ? "
        f"ORDER BY {order_by} LIMIT 1",
        (ts_code, as_of_date),
    ).fetchone()
    return row


def update_fundamental_cache(
    symbol: str,
    *,
    until_date: str | None = None,
    db_path: Path | None = None,
) -> dict[str, int]:
    """增量同步单只股票的基本面缓存。"""

    sync_until = _normalize_until_date(until_date)
    conn = _get_connection(db_path)
    try:
        pro = _create_tushare_client()
        counts = {
            dataset.name: _sync_dataset(
                conn,
                pro,
                dataset,
                ts_code=symbol,
                until_date=sync_until,
            )
            for dataset in _DATASET_DEFINITIONS
        }
        conn.commit()
        return counts
    finally:
        conn.close()


def _maybe_refresh_cache(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    as_of_date: str,
) -> None:
    requires_refresh = any(
        (_get_last_synced_date(conn, ts_code=symbol, dataset=dataset.name) or "") < as_of_date
        for dataset in _DATASET_DEFINITIONS
    )
    if not requires_refresh:
        return

    try:
        pro = _create_tushare_client()
        for dataset in _DATASET_DEFINITIONS:
            _sync_dataset(conn, pro, dataset, ts_code=symbol, until_date=as_of_date)
        conn.commit()
    except DataLoadError:
        if not _has_any_cached_rows(conn, symbol):
            raise


def load_financial_at(
    symbol: str,
    as_of_date: str,
    *,
    db_path: Path | None = None,
) -> FinancialSnapshot | None:
    """返回截至 as_of_date 已可见的最新基本面快照。

    财报类表严格使用 `ann_date <= as_of_date` 过滤，绝不按 `end_date`
    进行时间穿越。`daily_basic` 使用最近一个 `trade_date <= as_of_date`
    的估值快照补充估值字段。
    """

    yyyymmdd = as_of_date.replace("-", "")

    conn = _get_connection(db_path)
    try:
        _maybe_refresh_cache(conn, symbol=symbol, as_of_date=yyyymmdd)

        daily_basic = _query_latest_row(
            conn,
            _DATASET_REGISTRY["daily_basic"],
            ts_code=symbol,
            as_of_date=yyyymmdd,
        )
        indicator = _query_latest_row(
            conn,
            _DATASET_REGISTRY["fina_indicator"],
            ts_code=symbol,
            as_of_date=yyyymmdd,
        )
        income = _query_latest_row(
            conn,
            _DATASET_REGISTRY["income"],
            ts_code=symbol,
            as_of_date=yyyymmdd,
        )
        balance = _query_latest_row(
            conn,
            _DATASET_REGISTRY["balancesheet"],
            ts_code=symbol,
            as_of_date=yyyymmdd,
        )
        cashflow = _query_latest_row(
            conn,
            _DATASET_REGISTRY["cashflow"],
            ts_code=symbol,
            as_of_date=yyyymmdd,
        )

        anchor = indicator or income or balance or cashflow
        if anchor is None:
            return None

        return FinancialSnapshot(
            ts_code=str(anchor["ts_code"]),
            ann_date=str(anchor["ann_date"]),
            end_date=str(anchor["end_date"]),
            trade_date=str(daily_basic["trade_date"]) if daily_basic is not None else None,
            eps=_coalesce(indicator["eps"] if indicator is not None else None),
            bps=_coalesce(indicator["bps"] if indicator is not None else None),
            roe=_coalesce(indicator["roe"] if indicator is not None else None),
            roe_dt=_coalesce(indicator["roe_dt"] if indicator is not None else None),
            roa=_coalesce(indicator["roa"] if indicator is not None else None),
            grossprofit_margin=_coalesce(indicator["grossprofit_margin"] if indicator is not None else None),
            netprofit_margin=_coalesce(indicator["netprofit_margin"] if indicator is not None else None),
            current_ratio=_coalesce(indicator["current_ratio"] if indicator is not None else None),
            quick_ratio=_coalesce(indicator["quick_ratio"] if indicator is not None else None),
            assets_turn=_coalesce(indicator["assets_turn"] if indicator is not None else None),
            total_revenue=_coalesce(income["total_revenue"] if income is not None else None),
            revenue=_coalesce(income["revenue"] if income is not None else None),
            operate_profit=_coalesce(income["operate_profit"] if income is not None else None),
            total_profit=_coalesce(income["total_profit"] if income is not None else None),
            net_profit=_coalesce(
                income["n_income_attr_p"] if income is not None else None,
                income["n_income"] if income is not None else None,
            ),
            total_assets=_coalesce(balance["total_assets"] if balance is not None else None),
            total_liab=_coalesce(balance["total_liab"] if balance is not None else None),
            equity=_coalesce(
                balance["total_hldr_eqy_exc_min_int"] if balance is not None else None,
                balance["total_hldr_eqy_inc_min_int"] if balance is not None else None,
            ),
            money_cap=_coalesce(balance["money_cap"] if balance is not None else None),
            n_cashflow_act=_coalesce(cashflow["n_cashflow_act"] if cashflow is not None else None),
            n_cashflow_inv_act=_coalesce(cashflow["n_cashflow_inv_act"] if cashflow is not None else None),
            n_cashflow_fnc_act=_coalesce(cashflow["n_cash_flows_fnc_act"] if cashflow is not None else None),
            pe=_coalesce(daily_basic["pe"] if daily_basic is not None else None),
            pe_ttm=_coalesce(daily_basic["pe_ttm"] if daily_basic is not None else None),
            pb=_coalesce(daily_basic["pb"] if daily_basic is not None else None),
            ps=_coalesce(daily_basic["ps"] if daily_basic is not None else None),
            ps_ttm=_coalesce(daily_basic["ps_ttm"] if daily_basic is not None else None),
            dv_ratio=_coalesce(daily_basic["dv_ratio"] if daily_basic is not None else None),
            dv_ttm=_coalesce(daily_basic["dv_ttm"] if daily_basic is not None else None),
            total_share=_coalesce(daily_basic["total_share"] if daily_basic is not None else None),
            float_share=_coalesce(daily_basic["float_share"] if daily_basic is not None else None),
            free_share=_coalesce(daily_basic["free_share"] if daily_basic is not None else None),
            total_mv=_coalesce(daily_basic["total_mv"] if daily_basic is not None else None),
            circ_mv=_coalesce(daily_basic["circ_mv"] if daily_basic is not None else None),
        )
    finally:
        conn.close()
