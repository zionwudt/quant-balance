"""信号对象、持久化与查询。

文件结构：
1. 常量定义 (行 20-23)
   - SIGNAL_TIMEZONE: 时区（Asia/Shanghai）
   - VALID_SIGNAL_SIDES: 支持的信号方向（BUY/SELL）
   - VALID_SIGNAL_STATUSES: 支持的信号状态（pending/executed/ignored/expired）
   - TRACKING_WINDOWS: 收益跟踪窗口（1/5/10/20 日）

2. SQL Schema 定义 (行 25-94)
   - signals 表结构
   - 索引定义
   - 字段迁移脚本

3. Signal 数据类 (行 111-169)
   - 可持久化的交易信号对象

4. 工具函数 (行 172-321)
   - signal_now(): 当前时间
   - normalize_*(): 规范化函数
   - resolve_signal_name(): 解析股票中文名
   - suggest_signal_quantity(): 估算买入数量

5. 持久化函数 (行 211-356)
   - get_signal_connection(): 获取数据库连接
   - ensure_signal_schema(): 创建/升级表结构
   - persist_signals(): 批量保存信号

6. 查询函数 (行 359-479)
   - list_recent_signals(): 最近信号
   - list_today_signals(): 当日信号
   - list_signal_history(): 历史信号分页查询
   - update_signal_status(): 更新信号状态

7. 序列化函数 (行 482-625)
   - serialize_signal(): Signal 对象转字典
   - _serialize_signal_payload(): 补充显示用字段

8. 跟踪逻辑 (行 661-775)
   - _refresh_tracking(): 刷新信号收益跟踪数据
   - _compute_tracking_returns(): 计算窗口收益
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd

from quant_balance.data.common import CACHE_DB_PATH
from quant_balance.data.market_loader import load_dataframe
from quant_balance.data.stock_pool import filter_pool_at_date
from quant_balance.services.symbol_search_service import BENCHMARK_PRESETS

SIGNAL_TIMEZONE = ZoneInfo("Asia/Shanghai")
VALID_SIGNAL_SIDES = frozenset({"BUY", "SELL", "SHORT", "COVER"})
VALID_SIGNAL_STATUSES = frozenset({"pending", "executed", "ignored", "expired"})
TRACKING_WINDOWS = (1, 5, 10, 20)

_CREATE_SIGNALS_SQL = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    name TEXT,
    side TEXT NOT NULL,
    strategy TEXT NOT NULL,
    reason TEXT,
    price REAL,
    suggested_qty INTEGER,
    generated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    trade_date TEXT,
    asset_type TEXT NOT NULL DEFAULT 'stock',
    source TEXT NOT NULL DEFAULT 'scheduler',
    scan_id TEXT,
    rank INTEGER,
    score REAL,
    total_return REAL,
    sharpe_ratio REAL,
    max_drawdown REAL,
    total_trades INTEGER,
    win_rate REAL,
    profit_factor REAL,
    final_value REAL,
    raw_payload TEXT NOT NULL DEFAULT '{}',
    return_1d_pct REAL,
    return_5d_pct REAL,
    return_10d_pct REAL,
    return_20d_pct REAL,
    tracking_updated_at TEXT,
    updated_at TEXT
);
"""

_CREATE_SIGNAL_INDEXES_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals (created_at DESC, id DESC);",
    "CREATE INDEX IF NOT EXISTS idx_signals_trade_date ON signals (trade_date, strategy, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_signals_status ON signals (status, created_at DESC);",
)

_SIGNAL_MIGRATION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("name", "TEXT"),
    ("reason", "TEXT"),
    ("price", "REAL"),
    ("suggested_qty", "INTEGER"),
    ("created_at", "TEXT"),
    ("status", "TEXT DEFAULT 'pending'"),
    ("trade_date", "TEXT"),
    ("asset_type", "TEXT DEFAULT 'stock'"),
    ("source", "TEXT DEFAULT 'scheduler'"),
    ("scan_id", "TEXT"),
    ("rank", "INTEGER"),
    ("score", "REAL"),
    ("total_return", "REAL"),
    ("sharpe_ratio", "REAL"),
    ("max_drawdown", "REAL"),
    ("total_trades", "INTEGER"),
    ("win_rate", "REAL"),
    ("profit_factor", "REAL"),
    ("final_value", "REAL"),
    ("raw_payload", "TEXT DEFAULT '{}'"),
    ("return_1d_pct", "REAL"),
    ("return_5d_pct", "REAL"),
    ("return_10d_pct", "REAL"),
    ("return_20d_pct", "REAL"),
    ("tracking_updated_at", "TEXT"),
    ("updated_at", "TEXT"),
)

_SIGNAL_REASON_TEMPLATES = {
    "sma_cross": "均线金叉候选",
    "ema_cross": "EMA 多头候选",
    "macd": "MACD 多头候选",
    "rsi": "RSI 超卖反弹候选",
    "bollinger": "布林带突破候选",
    "grid": "网格回补候选",
    "dca": "定投加仓候选",
    "ma_rsi_filter": "均线趋势过滤候选",
    "buy_and_hold": "买入并持有候选",
}

_BENCHMARK_NAME_MAP = {item["symbol"]: item["name"] for item in BENCHMARK_PRESETS}


@dataclass(slots=True)
class Signal:
    """可持久化的交易信号。"""

    symbol: str
    name: str
    side: str
    strategy: str
    reason: str
    price: float
    suggested_qty: int
    timestamp: datetime
    asset_type: str = "stock"
    trade_date: str | None = None
    status: str = "pending"
    scan_id: str | None = None
    rank: int | None = None
    score: float | None = None
    source: str = "scheduler"
    raw_payload: dict[str, object] = field(default_factory=dict)
    total_return: float | None = None
    sharpe_ratio: float | None = None
    max_drawdown: float | None = None
    total_trades: int | None = None
    win_rate: float | None = None
    profit_factor: float | None = None
    final_value: float | None = None
    id: int | None = None
    return_1d_pct: float | None = None
    return_5d_pct: float | None = None
    return_10d_pct: float | None = None
    return_20d_pct: float | None = None
    tracking_updated_at: str | None = None

    def __post_init__(self) -> None:
        self.symbol = str(self.symbol).strip().upper()
        self.name = str(self.name or self.symbol).strip() or self.symbol
        self.side = normalize_signal_side(self.side)
        self.strategy = str(self.strategy).strip()
        self.reason = str(self.reason or default_signal_reason(self.strategy)).strip()
        self.price = 0.0 if self.price in (None, "") else float(self.price)
        self.suggested_qty = (
            0 if self.suggested_qty in (None, "") else int(self.suggested_qty)
        )
        self.asset_type = str(self.asset_type or "stock").strip() or "stock"
        self.status = normalize_signal_status(self.status)
        self.trade_date = normalize_trade_date(
            self.trade_date or self.timestamp.date().isoformat()
        )
        self.rank = None if self.rank in (None, "") else int(self.rank)
        self.score = None if self.score in (None, "") else float(self.score)
        self.total_return = optional_float(self.total_return)
        self.sharpe_ratio = optional_float(self.sharpe_ratio)
        self.max_drawdown = optional_float(self.max_drawdown)
        self.total_trades = optional_int(self.total_trades)
        self.win_rate = optional_float(self.win_rate)
        self.profit_factor = optional_float(self.profit_factor)
        self.final_value = optional_float(self.final_value)
        self.return_1d_pct = optional_float(self.return_1d_pct)
        self.return_5d_pct = optional_float(self.return_5d_pct)
        self.return_10d_pct = optional_float(self.return_10d_pct)
        self.return_20d_pct = optional_float(self.return_20d_pct)
        self.raw_payload = dict(self.raw_payload or {})


def signal_now() -> datetime:
    return datetime.now(tz=SIGNAL_TIMEZONE)


def current_signal_date() -> date:
    return signal_now().date()


def normalize_trade_date(value: str) -> str:
    return datetime.fromisoformat(str(value)).date().isoformat()


def normalize_signal_side(value: str) -> str:
    side = str(value or "").strip().upper()
    if side not in VALID_SIGNAL_SIDES:
        raise ValueError(f"不支持的信号方向 {value!r}，当前支持: BUY / SELL")
    return side


def normalize_signal_status(value: str) -> str:
    status = str(value or "").strip().lower()
    if status not in VALID_SIGNAL_STATUSES:
        supported = ", ".join(sorted(VALID_SIGNAL_STATUSES))
        raise ValueError(f"不支持的信号状态 {value!r}，当前支持: {supported}")
    return status


def optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def get_signal_connection(*, db_path: Path | None = None) -> sqlite3.Connection:
    """获取信号 SQLite 连接并完成 schema 迁移。"""

    from quant_balance.data.connection import get_shared_connection

    conn = get_shared_connection(db_path)
    ensure_signal_schema(conn)
    return conn


def ensure_signal_schema(conn: sqlite3.Connection) -> None:
    """创建或升级 signals 表。"""

    conn.execute(_CREATE_SIGNALS_SQL)
    existing_columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(signals)").fetchall()
    }
    for name, column_sql in _SIGNAL_MIGRATION_COLUMNS:
        if name in existing_columns:
            continue
        conn.execute(f"ALTER TABLE signals ADD COLUMN {name} {column_sql}")

    for sql in _CREATE_SIGNAL_INDEXES_SQL:
        conn.execute(sql)

    conn.execute(
        "UPDATE signals SET created_at = COALESCE(NULLIF(created_at, ''), generated_at) "
        "WHERE created_at IS NULL OR created_at = ''"
    )
    conn.execute(
        "UPDATE signals SET name = COALESCE(NULLIF(name, ''), symbol) "
        "WHERE name IS NULL OR name = ''"
    )
    conn.execute(
        "UPDATE signals SET reason = COALESCE(NULLIF(reason, ''), strategy) "
        "WHERE reason IS NULL OR reason = ''"
    )
    conn.execute(
        "UPDATE signals SET status = COALESCE(NULLIF(status, ''), 'pending') "
        "WHERE status IS NULL OR status = ''"
    )
    conn.execute(
        "UPDATE signals SET raw_payload = COALESCE(NULLIF(raw_payload, ''), '{}') "
        "WHERE raw_payload IS NULL OR raw_payload = ''"
    )
    conn.commit()


def default_signal_reason(
    strategy: str, *, rank: int | None = None, score: float | None = None
) -> str:
    """根据策略名生成默认信号原因。"""

    reason = _SIGNAL_REASON_TEMPLATES.get(strategy, f"{strategy} 策略触发")
    if rank is not None:
        reason = f"{reason}，排名 #{rank}"
    if score is not None:
        reason = f"{reason}，评分 {score:.2f}"
    return reason


def resolve_signal_name(
    symbol: str,
    *,
    trade_date: str | None = None,
    asset_type: str = "stock",
    fallback_name: str | None = None,
    db_path: Path | None = None,
) -> str:
    """尽量解析信号对应的中文名称。"""

    if fallback_name and str(fallback_name).strip():
        return str(fallback_name).strip()

    normalized = str(symbol).strip().upper()
    if normalized in _BENCHMARK_NAME_MAP:
        return _BENCHMARK_NAME_MAP[normalized]
    if asset_type != "stock" or not trade_date:
        return normalized

    try:
        records = filter_pool_at_date(
            normalize_trade_date(trade_date),
            symbols=[normalized],
            db_path=db_path,
        )
    except Exception:  # noqa: BLE001
        return normalized
    if not records:
        return normalized
    return records[0].name or normalized


def suggest_signal_quantity(
    *,
    price: float | None,
    cash: float,
    asset_type: str = "stock",
    slots: int = 1,
) -> int:
    """按等权资金粗略估算建议数量。"""

    signal_price = optional_float(price)
    if signal_price is None or signal_price <= 0 or cash <= 0:
        return 0

    lot_size = 10 if asset_type == "convertible_bond" else 100
    slot_count = max(1, int(slots))
    budget = float(cash) / slot_count
    lots = int(budget // (signal_price * lot_size))
    return max(0, lots * lot_size)


def persist_signals(
    signals: Iterable[Signal],
    *,
    replace_trade_date: str | None = None,
    replace_strategies: list[str] | None = None,
    replace_source: str = "scheduler",
    db_path: Path | None = None,
) -> None:
    """持久化信号列表，并可按扫描范围覆盖旧信号。"""

    items = list(signals)
    with get_signal_connection(db_path=db_path) as conn:
        if replace_trade_date and replace_strategies:
            placeholders = ", ".join("?" for _ in replace_strategies)
            conn.execute(
                f"DELETE FROM signals WHERE trade_date = ? AND strategy IN ({placeholders}) AND source = ?",
                [
                    normalize_trade_date(replace_trade_date),
                    *replace_strategies,
                    replace_source,
                ],
            )

        conn.executemany(
            "INSERT INTO signals "
            "("
            "symbol, name, side, strategy, reason, price, suggested_qty, generated_at, created_at, status, "
            "trade_date, asset_type, source, scan_id, rank, score, total_return, sharpe_ratio, max_drawdown, "
            "total_trades, win_rate, profit_factor, final_value, raw_payload, return_1d_pct, return_5d_pct, "
            "return_10d_pct, return_20d_pct, tracking_updated_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [_signal_insert_values(signal) for signal in items],
        )
        conn.commit()


def list_recent_signals(
    *,
    limit: int = 20,
    trade_date: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, object]]:
    """读取最近持久化的信号列表。"""

    normalized_limit = max(1, min(int(limit), 200))
    query = "SELECT * FROM signals "
    params: list[object] = []
    if trade_date:
        query += "WHERE trade_date = ? "
        params.append(normalize_trade_date(trade_date))
    query += "ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(normalized_limit)

    rows = _fetch_signal_rows(query, params, db_path=db_path)
    _refresh_tracking(rows, db_path=db_path)
    return rows


def list_today_signals(
    *,
    as_of_date: str | None = None,
    limit: int = 200,
    db_path: Path | None = None,
) -> dict[str, object]:
    """返回指定自然日生成的信号。"""

    normalized_date = normalize_trade_date(
        as_of_date or current_signal_date().isoformat()
    )
    normalized_limit = max(1, min(int(limit), 500))
    rows = _fetch_signal_rows(
        "SELECT * FROM signals WHERE substr(created_at, 1, 10) = ? ORDER BY created_at DESC, id DESC LIMIT ?",
        [normalized_date, normalized_limit],
        db_path=db_path,
    )
    _refresh_tracking(rows, db_path=db_path)
    return {
        "date": normalized_date,
        "total": len(rows),
        "items": rows,
    }


def list_signal_history(
    *,
    days: int = 30,
    page: int = 1,
    page_size: int = 20,
    db_path: Path | None = None,
) -> dict[str, object]:
    """按天数窗口查询历史信号，并支持分页。"""

    normalized_days = max(1, min(int(days), 3650))
    normalized_page = max(1, int(page))
    normalized_page_size = max(1, min(int(page_size), 200))
    start_date = (
        current_signal_date() - timedelta(days=normalized_days - 1)
    ).isoformat()
    offset = (normalized_page - 1) * normalized_page_size

    with get_signal_connection(db_path=db_path) as conn:
        total = int(
            conn.execute(
                "SELECT COUNT(*) FROM signals WHERE substr(created_at, 1, 10) >= ?",
                (start_date,),
            ).fetchone()[0]
        )

    rows = _fetch_signal_rows(
        "SELECT * FROM signals WHERE substr(created_at, 1, 10) >= ? "
        "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        [start_date, normalized_page_size, offset],
        db_path=db_path,
    )
    _refresh_tracking(rows, db_path=db_path)
    return {
        "days": normalized_days,
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "has_more": normalized_page * normalized_page_size < total,
        "items": rows,
    }


def update_signal_status(
    signal_id: int,
    *,
    status: str,
    db_path: Path | None = None,
) -> dict[str, object]:
    """更新信号状态。"""

    normalized_status = normalize_signal_status(status)
    normalized_id = int(signal_id)
    updated_at = signal_now().isoformat()

    with get_signal_connection(db_path=db_path) as conn:
        cursor = conn.execute(
            "UPDATE signals SET status = ?, updated_at = ? WHERE id = ?",
            (normalized_status, updated_at, normalized_id),
        )
        conn.commit()
        if cursor.rowcount < 1:
            raise LookupError(f"信号 {normalized_id} 不存在。")

    return get_signal_by_id(normalized_id, db_path=db_path)


def get_signal_by_id(
    signal_id: int, *, db_path: Path | None = None
) -> dict[str, object]:
    """读取单条信号。"""

    rows = _fetch_signal_rows(
        "SELECT * FROM signals WHERE id = ? LIMIT 1",
        [int(signal_id)],
        db_path=db_path,
    )
    if not rows:
        raise LookupError(f"信号 {signal_id} 不存在。")
    _refresh_tracking(rows, db_path=db_path)
    return rows[0]


def serialize_signal(signal: Signal) -> dict[str, object]:
    """序列化内存中的 Signal 对象。"""

    created_at = signal.timestamp.isoformat()
    return _serialize_signal_payload(
        {
            "id": signal.id,
            "symbol": signal.symbol,
            "name": signal.name,
            "side": signal.side,
            "strategy": signal.strategy,
            "reason": signal.reason,
            "price": signal.price,
            "suggested_qty": signal.suggested_qty,
            "generated_at": created_at,
            "created_at": created_at,
            "status": signal.status,
            "trade_date": signal.trade_date,
            "asset_type": signal.asset_type,
            "source": signal.source,
            "scan_id": signal.scan_id,
            "rank": signal.rank,
            "score": signal.score,
            "total_return": signal.total_return,
            "sharpe_ratio": signal.sharpe_ratio,
            "max_drawdown": signal.max_drawdown,
            "total_trades": signal.total_trades,
            "win_rate": signal.win_rate,
            "profit_factor": signal.profit_factor,
            "final_value": signal.final_value,
            "raw_payload": dict(signal.raw_payload or {}),
            "return_1d_pct": signal.return_1d_pct,
            "return_5d_pct": signal.return_5d_pct,
            "return_10d_pct": signal.return_10d_pct,
            "return_20d_pct": signal.return_20d_pct,
            "tracking_updated_at": signal.tracking_updated_at,
        }
    )


def _signal_insert_values(signal: Signal) -> tuple[object, ...]:
    created_at = signal.timestamp.isoformat()
    return (
        signal.symbol,
        signal.name,
        signal.side,
        signal.strategy,
        signal.reason,
        signal.price,
        signal.suggested_qty,
        created_at,
        created_at,
        signal.status,
        signal.trade_date,
        signal.asset_type,
        signal.source,
        signal.scan_id,
        signal.rank,
        signal.score,
        signal.total_return,
        signal.sharpe_ratio,
        signal.max_drawdown,
        signal.total_trades,
        signal.win_rate,
        signal.profit_factor,
        signal.final_value,
        json.dumps(signal.raw_payload, ensure_ascii=False, sort_keys=True),
        signal.return_1d_pct,
        signal.return_5d_pct,
        signal.return_10d_pct,
        signal.return_20d_pct,
        signal.tracking_updated_at,
        created_at,
    )


def _fetch_signal_rows(
    query: str,
    params: list[object],
    *,
    db_path: Path | None = None,
) -> list[dict[str, object]]:
    with get_signal_connection(db_path=db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_deserialize_signal_row(row) for row in rows]


def _deserialize_signal_row(row: sqlite3.Row) -> dict[str, object]:
    payload = {
        "id": row["id"],
        "symbol": str(row["symbol"] or "").upper(),
        "name": str(row["name"] or row["symbol"] or ""),
        "side": normalize_signal_side(str(row["side"] or "BUY")),
        "strategy": str(row["strategy"] or ""),
        "reason": str(row["reason"] or row["strategy"] or ""),
        "price": optional_float(row["price"]),
        "suggested_qty": optional_int(row["suggested_qty"]) or 0,
        "generated_at": str(row["generated_at"] or row["created_at"] or ""),
        "created_at": str(row["created_at"] or row["generated_at"] or ""),
        "status": normalize_signal_status(str(row["status"] or "pending")),
        "trade_date": str(row["trade_date"] or "") or str(row["created_at"] or "")[:10],
        "asset_type": str(row["asset_type"] or "stock"),
        "source": str(row["source"] or "scheduler"),
        "scan_id": row["scan_id"],
        "rank": optional_int(row["rank"]),
        "score": optional_float(row["score"]),
        "total_return": optional_float(row["total_return"]),
        "sharpe_ratio": optional_float(row["sharpe_ratio"]),
        "max_drawdown": optional_float(row["max_drawdown"]),
        "total_trades": optional_int(row["total_trades"]),
        "win_rate": optional_float(row["win_rate"]),
        "profit_factor": optional_float(row["profit_factor"]),
        "final_value": optional_float(row["final_value"]),
        "raw_payload": json.loads(row["raw_payload"] or "{}"),
        "return_1d_pct": optional_float(row["return_1d_pct"]),
        "return_5d_pct": optional_float(row["return_5d_pct"]),
        "return_10d_pct": optional_float(row["return_10d_pct"]),
        "return_20d_pct": optional_float(row["return_20d_pct"]),
        "tracking_updated_at": str(row["tracking_updated_at"] or "") or None,
        "updated_at": str(row["updated_at"] or "") or None,
    }
    return _serialize_signal_payload(payload)


def _serialize_signal_payload(payload: dict[str, object]) -> dict[str, object]:
    side = normalize_signal_side(str(payload["side"]))
    status = normalize_signal_status(str(payload["status"]))
    signal_price = optional_float(payload.get("price"))
    signal_payload = {
        **payload,
        "side": side,
        "side_label": {"BUY": "买入", "SELL": "卖出", "SHORT": "做空", "COVER": "平空"}.get(side, side),
        "status": status,
        "status_label": _signal_status_label(status),
        "price": signal_price,
        "signal_price": signal_price,
        "trigger_reason": str(payload.get("reason") or ""),
        "generated_at": payload.get("generated_at"),
        "created_at": payload.get("created_at"),
        "performance_1d_pct": _directional_return(side, payload.get("return_1d_pct")),
        "performance_5d_pct": _directional_return(side, payload.get("return_5d_pct")),
        "performance_10d_pct": _directional_return(side, payload.get("return_10d_pct")),
        "performance_20d_pct": _directional_return(side, payload.get("return_20d_pct")),
    }
    signal_payload["outcome_label"] = _build_outcome_label(signal_payload)
    return signal_payload


def _signal_status_label(status: str) -> str:
    return {
        "pending": "待处理",
        "executed": "已执行",
        "ignored": "已忽略",
        "expired": "已过期",
    }[status]


def _directional_return(side: str, value: object) -> float | None:
    raw = optional_float(value)
    if raw is None:
        return None
    return round((-raw if side in ("SELL", "SHORT") else raw), 4)


def _build_outcome_label(payload: dict[str, object]) -> str:
    status = str(payload["status"])
    if status == "executed":
        return "已执行"
    if status == "ignored":
        return "已忽略"
    if status == "expired":
        return "已过期"

    for key in ("performance_20d_pct", "performance_10d_pct", "performance_5d_pct"):
        performance = optional_float(payload.get(key))
        if performance is None:
            continue
        return "信号有效" if performance >= 0 else "信号失效"
    return "跟踪中"


def _refresh_tracking(
    rows: list[dict[str, object]], *, db_path: Path | None = None
) -> None:
    candidates = [row for row in rows if _should_refresh_tracking(row)]
    if not candidates:
        return

    end_date = current_signal_date().isoformat()
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for row in candidates:
        signal_date = str(row.get("trade_date") or row.get("created_at") or "")[:10]
        if not signal_date or signal_date >= end_date:
            continue
        key = (str(row["symbol"]), str(row.get("asset_type") or "stock"))
        group = grouped.setdefault(key, {"start_date": signal_date, "rows": []})
        if signal_date < str(group["start_date"]):
            group["start_date"] = signal_date
        group["rows"].append(row)

    if not grouped:
        return

    updates: list[
        tuple[
            float | None, float | None, float | None, float | None, float, str, str, int
        ]
    ] = []
    tracking_updated_at = signal_now().isoformat()
    for (symbol, asset_type), group in grouped.items():
        try:
            frame = load_dataframe(
                symbol,
                str(group["start_date"]),
                end_date,
                asset_type=asset_type,  # type: ignore[arg-type]
                db_path=db_path,
            )
        except Exception:  # noqa: BLE001
            continue
        for row in group["rows"]:
            returns, signal_price = _compute_tracking_returns(row, frame)
            if returns is None:
                continue
            row["price"] = signal_price
            row["signal_price"] = signal_price
            row["return_1d_pct"] = returns[1]
            row["return_5d_pct"] = returns[5]
            row["return_10d_pct"] = returns[10]
            row["return_20d_pct"] = returns[20]
            row["tracking_updated_at"] = tracking_updated_at
            row["performance_1d_pct"] = _directional_return(
                str(row["side"]), returns[1]
            )
            row["performance_5d_pct"] = _directional_return(
                str(row["side"]), returns[5]
            )
            row["performance_10d_pct"] = _directional_return(
                str(row["side"]), returns[10]
            )
            row["performance_20d_pct"] = _directional_return(
                str(row["side"]), returns[20]
            )
            row["outcome_label"] = _build_outcome_label(row)
            updates.append(
                (
                    returns[1],
                    returns[5],
                    returns[10],
                    returns[20],
                    signal_price,
                    tracking_updated_at,
                    tracking_updated_at,
                    int(row["id"]),
                )
            )

    if not updates:
        return

    with get_signal_connection(db_path=db_path) as conn:
        conn.executemany(
            "UPDATE signals SET "
            "return_1d_pct = ?, return_5d_pct = ?, return_10d_pct = ?, return_20d_pct = ?, "
            "price = ?, tracking_updated_at = ?, updated_at = ? "
            "WHERE id = ?",
            updates,
        )
        conn.commit()


def _should_refresh_tracking(row: dict[str, object]) -> bool:
    signal_date = str(row.get("trade_date") or row.get("created_at") or "")[:10]
    if not signal_date:
        return False
    if signal_date >= current_signal_date().isoformat():
        return False
    tracking_updated_at = str(row.get("tracking_updated_at") or "")[:10]
    if not tracking_updated_at:
        return True
    return tracking_updated_at < current_signal_date().isoformat()


def _compute_tracking_returns(
    row: dict[str, object],
    frame: pd.DataFrame,
) -> tuple[dict[int, float | None], float] | tuple[None, None]:
    if frame is None or frame.empty:
        return None, None

    target_date = str(row.get("trade_date") or row.get("created_at") or "")[:10]
    if not target_date:
        return None, None

    index = frame.index
    position = int(index.searchsorted(pd.Timestamp(target_date)))
    if position >= len(index):
        return None, None

    signal_price = optional_float(row.get("price"))
    if signal_price is None or signal_price <= 0:
        signal_price = float(frame.iloc[position]["Close"])

    returns: dict[int, float | None] = {}
    for window in TRACKING_WINDOWS:
        future_position = position + window
        if future_position >= len(frame):
            returns[window] = None
            continue
        future_close = float(frame.iloc[future_position]["Close"])
        returns[window] = round((future_close / signal_price - 1.0) * 100.0, 4)
    return returns, signal_price
