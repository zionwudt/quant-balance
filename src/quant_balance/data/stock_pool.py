"""历史时点股票池构建与过滤 —— 防止幸存者偏差。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import sqlite3
from pathlib import Path

from quant_balance.data.common import CACHE_DB_PATH, DataLoadError, load_tushare_token

_CREATE_STOCK_LIST_SQL = """
CREATE TABLE IF NOT EXISTS stock_list (
    ts_code   TEXT PRIMARY KEY,
    name      TEXT,
    list_date TEXT,
    delist_date TEXT,
    industry  TEXT,
    market    TEXT
);
"""

_CREATE_NAME_CHANGE_SQL = """
CREATE TABLE IF NOT EXISTS stock_name_changes (
    ts_code    TEXT NOT NULL,
    name       TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date   TEXT,
    PRIMARY KEY (ts_code, start_date, name)
);
"""

_CREATE_NAME_CHANGE_FETCH_LOG_SQL = """
CREATE TABLE IF NOT EXISTS stock_name_change_fetch_log (
    ts_code TEXT PRIMARY KEY
);
"""


@dataclass(slots=True)
class StockPoolFilters:
    """股票池过滤条件。"""

    industries: tuple[str, ...] = ()
    min_market_cap: float | None = None
    max_market_cap: float | None = None
    min_pe: float | None = None
    max_pe: float | None = None
    exclude_st: bool = False
    min_listing_days: int | None = None


@dataclass(slots=True)
class StockPoolRecord:
    """股票池记录。"""

    ts_code: str
    name: str
    list_date: str
    delist_date: str | None
    industry: str
    market: str
    listing_days: int
    is_st: bool
    pe: float | None = None
    total_mv: float | None = None


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or CACHE_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_STOCK_LIST_SQL)
    conn.execute(_CREATE_NAME_CHANGE_SQL)
    conn.execute(_CREATE_NAME_CHANGE_FETCH_LOG_SQL)
    return conn


def _is_cache_populated(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM stock_list").fetchone()
    return row[0] > 0


def _fetch_and_cache_stock_list(conn: sqlite3.Connection) -> None:
    """从 Tushare 全量拉取上市 + 退市股票并写入缓存。"""
    try:
        import tushare as ts
    except ImportError as exc:
        raise DataLoadError(
            "需要安装 tushare 才能获取股票列表，请运行：pip install tushare"
        ) from exc

    token = load_tushare_token()
    pro = ts.pro_api(token)

    rows: list[tuple] = []
    for status in ("L", "D", "P"):
        df = pro.stock_basic(
            list_status=status,
            fields="ts_code,name,list_date,delist_date,industry,market",
        )
        if df is None or df.empty:
            continue
        for _, record in df.iterrows():
            rows.append(
                (
                    record["ts_code"],
                    record.get("name", "") or "",
                    record.get("list_date", "") or "",
                    _normalize_date(record.get("delist_date")),
                    record.get("industry", "") or "",
                    record.get("market", "") or "",
                )
            )

    conn.executemany(
        "INSERT OR REPLACE INTO stock_list "
        "(ts_code, name, list_date, delist_date, industry, market) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


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


def _query_pool_rows(
    conn: sqlite3.Connection,
    *,
    date: str,
    symbols: set[str] | None = None,
) -> list[sqlite3.Row]:
    cursor = conn.execute(
        "SELECT ts_code, name, list_date, delist_date, industry, market "
        "FROM stock_list "
        "WHERE list_date <= ? AND (delist_date IS NULL OR delist_date > ?) "
        "ORDER BY ts_code",
        (date, date),
    )
    rows = cursor.fetchall()
    if symbols is None:
        return rows
    return [row for row in rows if row["ts_code"] in symbols]


def _normalize_filters(filters: StockPoolFilters | dict | None) -> StockPoolFilters:
    if filters is None:
        return StockPoolFilters()
    if isinstance(filters, StockPoolFilters):
        normalized = filters
    elif isinstance(filters, dict):
        industries = tuple(
            str(item).strip()
            for item in filters.get("industries", [])
            if str(item).strip()
        )
        min_listing_days = filters.get("min_listing_days")
        normalized = StockPoolFilters(
            industries=industries,
            min_market_cap=_optional_float(filters.get("min_market_cap")),
            max_market_cap=_optional_float(filters.get("max_market_cap")),
            min_pe=_optional_float(filters.get("min_pe")),
            max_pe=_optional_float(filters.get("max_pe")),
            exclude_st=bool(filters.get("exclude_st", False)),
            min_listing_days=int(min_listing_days) if min_listing_days is not None else None,
        )
    else:
        raise TypeError("filters 必须是 StockPoolFilters、dict 或 None")

    if normalized.min_market_cap is not None and normalized.min_market_cap < 0:
        raise ValueError("min_market_cap 必须 >= 0")
    if normalized.max_market_cap is not None and normalized.max_market_cap < 0:
        raise ValueError("max_market_cap 必须 >= 0")
    if (
        normalized.min_market_cap is not None
        and normalized.max_market_cap is not None
        and normalized.min_market_cap > normalized.max_market_cap
    ):
        raise ValueError("min_market_cap 不能大于 max_market_cap")
    if (
        normalized.min_pe is not None
        and normalized.max_pe is not None
        and normalized.min_pe > normalized.max_pe
    ):
        raise ValueError("min_pe 不能大于 max_pe")
    if normalized.min_listing_days is not None and normalized.min_listing_days < 0:
        raise ValueError("min_listing_days 必须 >= 0")
    return normalized


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _has_name_change_cache(conn: sqlite3.Connection, ts_code: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM stock_name_change_fetch_log WHERE ts_code = ?",
        (ts_code,),
    ).fetchone()
    return row is not None


def _fetch_and_cache_name_changes(conn: sqlite3.Connection, ts_code: str) -> None:
    try:
        import tushare as ts
    except ImportError as exc:
        raise DataLoadError(
            "需要安装 tushare 才能获取股票更名信息，请运行：pip install tushare"
        ) from exc

    token = load_tushare_token()
    pro = ts.pro_api(token)

    df = pro.namechange(
        ts_code=ts_code,
        fields="ts_code,name,start_date,end_date",
    )
    rows: list[tuple] = []
    if df is not None and not df.empty:
        for _, record in df.iterrows():
            start_date = _normalize_date(record.get("start_date"))
            if start_date is None:
                continue
            rows.append(
                (
                    record["ts_code"],
                    record.get("name", "") or "",
                    start_date,
                    _normalize_date(record.get("end_date")),
                )
            )

    conn.executemany(
        "INSERT OR REPLACE INTO stock_name_changes "
        "(ts_code, name, start_date, end_date) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.execute(
        "INSERT OR REPLACE INTO stock_name_change_fetch_log (ts_code) VALUES (?)",
        (ts_code,),
    )
    conn.commit()


def _resolve_name_at_date(
    conn: sqlite3.Connection,
    *,
    ts_code: str,
    date: str,
    fallback_name: str,
) -> str:
    if not _has_name_change_cache(conn, ts_code):
        try:
            _fetch_and_cache_name_changes(conn, ts_code)
        except Exception:  # noqa: BLE001
            return fallback_name

    row = conn.execute(
        "SELECT name FROM stock_name_changes "
        "WHERE ts_code = ? AND start_date <= ? "
        "AND (end_date IS NULL OR end_date = '' OR end_date > ?) "
        "ORDER BY start_date DESC LIMIT 1",
        (ts_code, date, date),
    ).fetchone()
    if row is None:
        return fallback_name
    return str(row["name"])


def _looks_like_st(name: str) -> bool:
    upper = name.upper().replace("ＳＴ", "ST")
    return "ST" in upper


def _listing_days(list_date: str, as_of_date: str) -> int:
    listed_at = datetime.strptime(list_date, "%Y%m%d")
    snapshot_at = datetime.strptime(as_of_date, "%Y%m%d")
    return (snapshot_at - listed_at).days


def _passes_range(value: float | None, minimum: float | None, maximum: float | None) -> bool:
    if minimum is None and maximum is None:
        return True
    if value is None:
        return False
    if minimum is not None and value < minimum:
        return False
    if maximum is not None and value > maximum:
        return False
    return True


def _load_snapshot_fields(
    ts_code: str,
    *,
    date: str,
    db_path: Path | None,
) -> tuple[float | None, float | None]:
    from quant_balance.data.fundamental_loader import load_financial_at

    snapshot = load_financial_at(ts_code, date, db_path=db_path)
    if snapshot is None:
        return None, None
    return snapshot.pe, snapshot.total_mv


def get_pool_at_date(
    date: str,
    *,
    db_path: Path | None = None,
) -> list[str]:
    """返回指定历史日期当天处于上市状态的股票代码列表。"""

    yyyymmdd = date.replace("-", "")
    conn = _get_connection(db_path)
    try:
        if not _is_cache_populated(conn):
            _fetch_and_cache_stock_list(conn)
        return [row["ts_code"] for row in _query_pool_rows(conn, date=yyyymmdd)]
    finally:
        conn.close()


def filter_pool_at_date(
    date: str,
    *,
    filters: StockPoolFilters | dict | None = None,
    symbols: list[str] | None = None,
    db_path: Path | None = None,
) -> list[StockPoolRecord]:
    """在历史股票池之上叠加过滤条件，返回结构化结果。"""

    yyyymmdd = date.replace("-", "")
    normalized_filters = _normalize_filters(filters)
    selected_symbols = set(symbols) if symbols is not None else None
    requires_snapshot = any(
        value is not None
        for value in (
            normalized_filters.min_market_cap,
            normalized_filters.max_market_cap,
            normalized_filters.min_pe,
            normalized_filters.max_pe,
        )
    )

    conn = _get_connection(db_path)
    try:
        if not _is_cache_populated(conn):
            _fetch_and_cache_stock_list(conn)

        rows = _query_pool_rows(conn, date=yyyymmdd, symbols=selected_symbols)
        records: list[StockPoolRecord] = []

        for row in rows:
            industry = str(row["industry"] or "")
            if normalized_filters.industries and industry not in normalized_filters.industries:
                continue

            listing_days = _listing_days(str(row["list_date"]), yyyymmdd)
            if (
                normalized_filters.min_listing_days is not None
                and listing_days < normalized_filters.min_listing_days
            ):
                continue

            fallback_name = str(row["name"] or "")
            current_name = fallback_name
            is_st = _looks_like_st(fallback_name)
            if normalized_filters.exclude_st:
                current_name = _resolve_name_at_date(
                    conn,
                    ts_code=str(row["ts_code"]),
                    date=yyyymmdd,
                    fallback_name=fallback_name,
                )
                is_st = _looks_like_st(current_name)
                if is_st:
                    continue

            pe = None
            total_mv = None
            if requires_snapshot:
                pe, total_mv = _load_snapshot_fields(
                    str(row["ts_code"]),
                    date=date,
                    db_path=db_path,
                )
                if not _passes_range(
                    total_mv,
                    normalized_filters.min_market_cap,
                    normalized_filters.max_market_cap,
                ):
                    continue
                if not _passes_range(
                    pe,
                    normalized_filters.min_pe,
                    normalized_filters.max_pe,
                ):
                    continue

            records.append(
                StockPoolRecord(
                    ts_code=str(row["ts_code"]),
                    name=current_name,
                    list_date=str(row["list_date"]),
                    delist_date=str(row["delist_date"]) if row["delist_date"] else None,
                    industry=industry,
                    market=str(row["market"] or ""),
                    listing_days=listing_days,
                    is_st=is_st,
                    pe=pe,
                    total_mv=total_mv,
                )
            )

        return records
    finally:
        conn.close()
