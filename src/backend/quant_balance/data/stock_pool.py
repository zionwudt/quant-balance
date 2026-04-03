"""历史时点股票池构建与过滤 —— 防止幸存者偏差。

核心概念：
- 幸存者偏差: 回测时只选择当前存活的股票会高估收益
- 历史股票池: 回测时使用当时实际上市的股票列表

功能：
- get_pool_at_date(): 获取指定日期的上市股票列表
- filter_pool_at_date(): 基于历史股票池叠加过滤条件
- 过滤条件: 行业、市值、PE、ST 状态、上市天数等
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import sqlite3
from pathlib import Path

from quant_balance.data.common import (
    CACHE_DB_PATH,
    DataLoadError,
    load_tushare_token,
    resolve_daily_provider_order,
)

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

_CREATE_STOCK_LIST_FETCH_LOG_SQL = """
CREATE TABLE IF NOT EXISTS stock_list_fetch_log (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_fetched_at TEXT NOT NULL
);
"""

# 超过此天数未刷新则触发增量更新
_CACHE_STALENESS_DAYS = 7


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
    conn.execute(_CREATE_STOCK_LIST_FETCH_LOG_SQL)
    return conn


def _is_cache_populated(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM stock_list").fetchone()
    return row[0] > 0


def _get_last_fetched_at(conn: sqlite3.Connection) -> datetime | None:
    row = conn.execute(
        "SELECT last_fetched_at FROM stock_list_fetch_log WHERE id = 1"
    ).fetchone()
    if row is None:
        return None
    text = str(row["last_fetched_at"] or "")
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _should_refresh_cache(conn: sqlite3.Connection) -> bool:
    """缓存超过 _CACHE_STALENESS_DAYS 天未更新时返回 True。"""
    last_fetched = _get_last_fetched_at(conn)
    if last_fetched is None:
        return True
    cutoff = datetime.now() - timedelta(days=_CACHE_STALENESS_DAYS)
    return last_fetched < cutoff


def _update_fetch_timestamp(conn: sqlite3.Connection) -> None:
    """更新 stock_list_fetch_log 时间戳。"""
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT OR REPLACE INTO stock_list_fetch_log (id, last_fetched_at) VALUES (1, ?)",
        (now,),
    )
    conn.commit()


def _resolve_stock_list_provider(data_provider: str | None) -> str:
    """确定用于股票列表的数据源。"""
    if data_provider:
        return data_provider.strip().lower()
    # 从全局配置读取首选数据源
    try:
        order = resolve_daily_provider_order()
        return order[0]
    except Exception:  # noqa: BLE001
        return "tushare"


def _fetch_and_cache_stock_list(
    conn: sqlite3.Connection,
    incremental: bool = False,
    *,
    data_provider: str | None = None,
) -> None:
    """从指定数据源拉取上市 + 退市股票并写入缓存。

    - 首次（全量）拉取：清空旧数据，写入所有记录
    - 增量拉取：只拉取 list_date >= 上次拉取时间 的新上市股票

    当 data_provider 为 None 时按全局配置优先级逐一尝试。
    """
    if data_provider:
        # 用户明确指定了数据源，只用该数据源
        _dispatch_stock_list_fetch(conn, data_provider.strip().lower(), incremental)
        return

    # 自动模式：按优先级尝试
    try:
        providers = resolve_daily_provider_order()
    except Exception:  # noqa: BLE001
        providers = ["tushare"]

    last_error: Exception | None = None
    for provider in providers:
        try:
            _dispatch_stock_list_fetch(conn, provider, incremental)
            return
        except DataLoadError as exc:
            last_error = exc
            continue

    if last_error is not None:
        raise last_error
    raise DataLoadError("无法获取股票列表，所有数据源均不可用。")


def _dispatch_stock_list_fetch(
    conn: sqlite3.Connection,
    provider: str,
    incremental: bool,
) -> None:
    """根据数据源调度股票列表拉取。"""
    if provider == "tushare":
        _fetch_stock_list_via_tushare(conn, incremental)
    elif provider in ("akshare", "baostock"):
        _fetch_stock_list_via_alternative(conn, provider=provider)
    else:
        raise DataLoadError(f"不支持的股票列表数据源: {provider}")


def _fetch_stock_list_via_alternative(
    conn: sqlite3.Connection,
    *,
    provider: str,
) -> None:
    """通过 AkShare 或 BaoStock 拉取股票列表并全量写入缓存。"""
    if provider == "akshare":
        from quant_balance.data.akshare_loader import fetch_stock_list
    elif provider == "baostock":
        from quant_balance.data.baostock_loader import fetch_stock_list
    else:
        raise DataLoadError(f"不支持的股票列表数据源: {provider}")

    try:
        raw_rows = fetch_stock_list()
    except Exception as exc:  # noqa: BLE001
        raise DataLoadError(f"获取股票列表失败（{provider}）：{exc}") from exc

    if not raw_rows:
        return

    rows: list[tuple] = []
    for ts_code, name, list_date, delist_date, industry, market in raw_rows:
        rows.append((
            str(ts_code),
            str(name or ""),
            _normalize_date(list_date) or "",
            _normalize_date(delist_date),
            str(industry or ""),
            str(market or ""),
        ))

    conn.execute("DELETE FROM stock_list")
    conn.executemany(
        "INSERT OR REPLACE INTO stock_list "
        "(ts_code, name, list_date, delist_date, industry, market) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    _update_fetch_timestamp(conn)


def _fetch_stock_list_via_tushare(conn: sqlite3.Connection, incremental: bool = False) -> None:
    """从 Tushare 拉取上市 + 退市股票并写入缓存。

    - 首次（全量）拉取：清空旧数据，写入所有记录
    - 增量拉取：只拉取 list_date >= 上次拉取时间 的新上市股票
    """
    try:
        import tushare as ts
    except ImportError as exc:
        raise DataLoadError(
            "需要安装 tushare 才能获取股票列表，请运行：pip install tushare"
        ) from exc

    token = load_tushare_token()
    pro = ts.pro_api(token)

    rows: list[tuple] = []
    try:
        if incremental:
            # 增量模式：只拉取新上市和退市变更的股票
            last_fetched = _get_last_fetched_at(conn)
            cutoff_date = (
                last_fetched.strftime("%Y%m%d") if last_fetched else None
            )
            for status in ("L", "P"):  # 上市 / 暂停上市
                df = pro.stock_basic(
                    list_status=status,
                    fields="ts_code,name,list_date,delist_date,industry,market",
                )
                if df is None or df.empty:
                    continue
                for _, record in df.iterrows():
                    list_date_val = record.get("list_date")
                    # 跳过已存在且未退市的记录
                    if cutoff_date and list_date_val:
                        if str(list_date_val) < cutoff_date:
                            # 检查是否已在缓存中
                            existing = conn.execute(
                                "SELECT 1 FROM stock_list WHERE ts_code = ?",
                                (str(record["ts_code"]),),
                            ).fetchone()
                            if existing:
                                continue
                    rows.append(
                        (
                            str(record["ts_code"]),
                            record.get("name", "") or "",
                            _normalize_date(list_date_val),
                            _normalize_date(record.get("delist_date")),
                            record.get("industry", "") or "",
                            record.get("market", "") or "",
                        )
                    )
            # 退市股票：L->D 变更
            df_delist = pro.stock_basic(
                list_status="D",
                fields="ts_code,name,list_date,delist_date,industry,market",
            )
            if df_delist is not None and not df_delist.empty:
                for _, record in df_delist.iterrows():
                    delist_date_val = record.get("delist_date")
                    if cutoff_date and delist_date_val:
                        if str(delist_date_val) < cutoff_date:
                            continue
                    rows.append(
                        (
                            str(record["ts_code"]),
                            record.get("name", "") or "",
                            _normalize_date(record.get("list_date")),
                            _normalize_date(delist_date_val),
                            record.get("industry", "") or "",
                            record.get("market", "") or "",
                        )
                    )
        else:
            # 全量模式
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
                            str(record["ts_code"]),
                            record.get("name", "") or "",
                            _normalize_date(record.get("list_date")),
                            _normalize_date(record.get("delist_date")),
                            record.get("industry", "") or "",
                            record.get("market", "") or "",
                        )
                    )
            # 全量写入前清空旧数据
            conn.execute("DELETE FROM stock_list")
    except Exception as exc:  # noqa: BLE001
        raise DataLoadError(f"获取股票列表失败：{exc}") from exc

    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO stock_list "
            "(ts_code, name, list_date, delist_date, industry, market) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
    _update_fetch_timestamp(conn)


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
        "WHERE (list_date = '' OR list_date <= ?) AND (delist_date IS NULL OR delist_date > ?) "
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
            min_listing_days=int(min_listing_days)
            if min_listing_days is not None
            else None,
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

    try:
        df = pro.namechange(
            ts_code=ts_code,
            fields="ts_code,name,start_date,end_date",
        )
    except Exception as exc:  # noqa: BLE001
        raise DataLoadError(f"获取股票更名信息失败：{exc}") from exc
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
    if not list_date or not list_date.strip():
        return -1  # 未知上市日期
    try:
        listed_at = datetime.strptime(list_date, "%Y%m%d")
        snapshot_at = datetime.strptime(as_of_date, "%Y%m%d")
        return (snapshot_at - listed_at).days
    except ValueError:
        return -1


def _passes_range(
    value: float | None, minimum: float | None, maximum: float | None
) -> bool:
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
    data_provider: str | None = None,
) -> list[str]:
    """返回指定历史日期当天处于上市状态的股票代码列表。"""

    yyyymmdd = date.replace("-", "")
    conn = _get_connection(db_path)
    try:
        if not _is_cache_populated(conn) or _should_refresh_cache(conn):
            _fetch_and_cache_stock_list(
                conn,
                incremental=True if _is_cache_populated(conn) else False,
                data_provider=data_provider,
            )
        return [row["ts_code"] for row in _query_pool_rows(conn, date=yyyymmdd)]
    finally:
        conn.close()


def search_stock_candidates(
    query: str,
    *,
    limit: int = 10,
    db_path: Path | None = None,
    data_provider: str | None = None,
) -> list[dict[str, str]]:
    """按代码/名称模糊搜索股票候选。"""

    normalized = str(query).strip()
    if not normalized or limit < 1:
        return []

    conn = _get_connection(db_path)
    try:
        if not _is_cache_populated(conn) or _should_refresh_cache(conn):
            _fetch_and_cache_stock_list(
                conn,
                incremental=True if _is_cache_populated(conn) else False,
                data_provider=data_provider,
            )

        code_exact = normalized.upper()
        code_prefix = f"{code_exact}%"
        code_like = f"%{code_exact}%"
        name_prefix = f"{normalized}%"
        name_like = f"%{normalized}%"
        rows = conn.execute(
            "SELECT ts_code, name, industry, market "
            "FROM stock_list "
            "WHERE UPPER(ts_code) LIKE ? OR name LIKE ? "
            "ORDER BY "
            "CASE "
            "  WHEN UPPER(ts_code) = ? THEN 0 "
            "  WHEN UPPER(ts_code) LIKE ? THEN 1 "
            "  WHEN name = ? THEN 2 "
            "  WHEN name LIKE ? THEN 3 "
            "  ELSE 4 "
            "END, ts_code "
            "LIMIT ?",
            (
                code_like,
                name_like,
                code_exact,
                code_prefix,
                normalized,
                name_prefix,
                limit,
            ),
        ).fetchall()
        return [
            {
                "symbol": str(row["ts_code"]),
                "name": str(row["name"] or ""),
                "industry": str(row["industry"] or ""),
                "market": str(row["market"] or ""),
                "asset_type": "stock",
            }
            for row in rows
        ]
    finally:
        conn.close()


def lookup_stock_metadata(
    symbols: list[str],
    *,
    db_path: Path | None = None,
) -> dict[str, dict[str, str]]:
    """从本地缓存读取股票名称/行业/市场；不主动触发远程拉取。"""

    normalized_symbols = sorted(
        {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
    )
    if not normalized_symbols:
        return {}

    path = db_path or CACHE_DB_PATH
    if not path.exists():
        return {}

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return {}
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in normalized_symbols)
        try:
            rows = conn.execute(
                f"SELECT ts_code, name, industry, market FROM stock_list WHERE ts_code IN ({placeholders})",
                normalized_symbols,
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
        return {
            str(row["ts_code"]): {
                "symbol": str(row["ts_code"]),
                "name": str(row["name"] or ""),
                "industry": str(row["industry"] or ""),
                "market": str(row["market"] or ""),
            }
            for row in rows
        }
    finally:
        conn.close()


def filter_pool_at_date(
    date: str,
    *,
    filters: StockPoolFilters | dict | None = None,
    symbols: list[str] | None = None,
    db_path: Path | None = None,
    data_provider: str | None = None,
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
        if not _is_cache_populated(conn) or _should_refresh_cache(conn):
            _fetch_and_cache_stock_list(
                conn,
                incremental=True if _is_cache_populated(conn) else False,
                data_provider=data_provider,
            )

        rows = _query_pool_rows(conn, date=yyyymmdd, symbols=selected_symbols)
        records: list[StockPoolRecord] = []

        for row in rows:
            industry = str(row["industry"] or "")
            if (
                normalized_filters.industries
                and industry not in normalized_filters.industries
            ):
                continue

            listing_days = _listing_days(str(row["list_date"]), yyyymmdd)
            if (
                normalized_filters.min_listing_days is not None
                and listing_days >= 0
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


# ── 可转债池支持 ──

_CREATE_CB_LIST_SQL = """
CREATE TABLE IF NOT EXISTS cb_list (
    ts_code TEXT PRIMARY KEY,
    bond_short_name TEXT,
    stk_code TEXT,
    stk_short_name TEXT,
    list_date TEXT,
    delist_date TEXT,
    maturity_date TEXT,
    par_value REAL,
    issue_size REAL,
    convert_price REAL
);
"""


@dataclass(slots=True)
class CbPoolRecord:
    """可转债池记录。"""

    ts_code: str
    bond_short_name: str
    stk_code: str
    stk_short_name: str
    list_date: str
    delist_date: str | None
    maturity_date: str | None
    par_value: float
    issue_size: float | None
    convert_price: float | None


def get_cb_pool_at_date(
    trade_date: str,
    *,
    db_path: Path | None = None,
) -> list[CbPoolRecord]:
    """获取指定日期仍在交易的可转债列表。"""

    conn = _get_connection(db_path)
    try:
        conn.execute(_CREATE_CB_LIST_SQL)
        count = conn.execute("SELECT COUNT(*) FROM cb_list").fetchone()[0]
        if count == 0:
            _fetch_and_cache_cb_list(conn)

        normalized_date = trade_date.replace("-", "")
        rows = conn.execute(
            "SELECT * FROM cb_list WHERE list_date <= ? AND (delist_date IS NULL OR delist_date > ?)",
            (normalized_date, normalized_date),
        ).fetchall()

        records: list[CbPoolRecord] = []
        for row in rows:
            records.append(CbPoolRecord(
                ts_code=str(row["ts_code"]),
                bond_short_name=str(row["bond_short_name"] or ""),
                stk_code=str(row["stk_code"] or ""),
                stk_short_name=str(row["stk_short_name"] or ""),
                list_date=str(row["list_date"] or ""),
                delist_date=str(row["delist_date"] or "") or None,
                maturity_date=str(row["maturity_date"] or "") or None,
                par_value=float(row["par_value"] or 100),
                issue_size=float(row["issue_size"]) if row["issue_size"] else None,
                convert_price=float(row["convert_price"]) if row["convert_price"] else None,
            ))
        return records
    finally:
        conn.close()


def _fetch_and_cache_cb_list(conn: sqlite3.Connection) -> None:
    """从 tushare 拉取可转债基础信息并缓存。"""
    try:
        import tushare as ts
    except ImportError as exc:
        raise DataLoadError("当前环境未安装 tushare，无法获取可转债列表。") from exc

    pro = ts.pro_api(load_tushare_token())
    df = pro.cb_basic(fields=[
        "ts_code", "bond_short_name", "stk_code", "stk_short_name",
        "list_date", "delist_date", "maturity_date", "par_value",
        "issue_size", "conv_price",
    ])
    if df is None or df.empty:
        return

    rows = []
    for _, row_data in df.iterrows():
        list_date = str(row_data.get("list_date") or "")
        if not list_date or list_date == "None":
            continue
        rows.append((
            str(row_data["ts_code"]),
            str(row_data.get("bond_short_name") or ""),
            str(row_data.get("stk_code") or ""),
            str(row_data.get("stk_short_name") or ""),
            list_date,
            str(row_data.get("delist_date") or "") or None,
            str(row_data.get("maturity_date") or "") or None,
            float(row_data.get("par_value") or 100),
            float(row_data["issue_size"]) if row_data.get("issue_size") else None,
            float(row_data["conv_price"]) if row_data.get("conv_price") else None,
        ))

    conn.executemany(
        "INSERT OR REPLACE INTO cb_list "
        "(ts_code, bond_short_name, stk_code, stk_short_name, list_date, delist_date, "
        "maturity_date, par_value, issue_size, convert_price) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
