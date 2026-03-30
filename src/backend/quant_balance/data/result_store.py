"""单股回测结果持久化与历史查询。"""

from __future__ import annotations

from datetime import datetime
import json
from math import ceil
from pathlib import Path
import sqlite3
from typing import Any, Iterable
from uuid import uuid4
from zoneinfo import ZoneInfo

from quant_balance.data.common import CACHE_DB_PATH

RESULT_STORE_TIMEZONE = ZoneInfo("Asia/Shanghai")

_CREATE_BACKTEST_RUNS_SQL = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    strategy TEXT NOT NULL,
    request_payload TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    trades_json TEXT,
    equity_curve_json TEXT,
    price_bars_json TEXT,
    chart_overlays_json TEXT,
    run_context_json TEXT
);
"""

_CREATE_BACKTEST_RUN_INDEXES_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_backtest_runs_created_at ON backtest_runs (created_at DESC, run_id DESC);",
    "CREATE INDEX IF NOT EXISTS idx_backtest_runs_symbol ON backtest_runs (symbol, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_backtest_runs_strategy ON backtest_runs (strategy, created_at DESC);",
)

_BACKTEST_RUN_MIGRATION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("price_bars_json", "TEXT"),
    ("chart_overlays_json", "TEXT"),
)

_SUMMARY_COMPARE_METRICS: tuple[tuple[str, str], ...] = (
    ("final_equity", "最终权益"),
    ("total_return_pct", "总收益率(%)"),
    ("annualized_return_pct", "年化收益率(%)"),
    ("sharpe_ratio", "Sharpe"),
    ("sortino_ratio", "Sortino"),
    ("max_drawdown_pct", "最大回撤(%)"),
    ("calmar_ratio", "Calmar"),
    ("trades_count", "交易笔数"),
    ("win_rate_pct", "胜率(%)"),
    ("profit_factor", "盈亏比"),
    ("expectancy_pct", "期望收益(%)"),
    ("benchmark_total_return_pct", "基准收益率(%)"),
    ("excess_return_pct", "超额收益(%)"),
    ("beta", "Beta"),
    ("alpha_annualized_pct", "Alpha(年化, %)"),
)


def result_store_now() -> str:
    """返回结果存储使用的当前时间。"""

    return datetime.now(tz=RESULT_STORE_TIMEZONE).isoformat(timespec="seconds")


def get_result_store_connection(*, db_path: Path | None = None) -> sqlite3.Connection:
    """获取结果存储 SQLite 连接并确保 schema 可用。"""

    path = db_path or CACHE_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    ensure_result_store_schema(conn)
    return conn


def ensure_result_store_schema(conn: sqlite3.Connection) -> None:
    """创建或升级 backtest_runs 表。"""

    conn.execute(_CREATE_BACKTEST_RUNS_SQL)
    existing_columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(backtest_runs)").fetchall()
    }
    for name, column_sql in _BACKTEST_RUN_MIGRATION_COLUMNS:
        if name in existing_columns:
            continue
        conn.execute(f"ALTER TABLE backtest_runs ADD COLUMN {name} {column_sql}")

    for sql in _CREATE_BACKTEST_RUN_INDEXES_SQL:
        conn.execute(sql)
    conn.commit()


def save_backtest_run(
    *,
    request_payload: dict[str, object],
    result_payload: dict[str, object],
    db_path: Path | None = None,
    run_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, object]:
    """保存单次回测结果。"""

    request = dict(request_payload or {})
    result = dict(result_payload or {})
    run_context = dict(result.get("run_context") or {})
    summary = dict(result.get("summary") or {})
    trades = list(result.get("trades") or [])
    equity_curve = list(result.get("equity_curve") or [])
    price_bars = list(result.get("price_bars") or [])
    chart_overlays = dict(result.get("chart_overlays") or {})

    symbol = str(run_context.get("symbol") or request.get("symbol") or "").strip().upper()
    strategy = str(run_context.get("strategy") or request.get("strategy") or "").strip()
    if not symbol:
        raise ValueError("缺少回测 symbol，无法保存结果")
    if not strategy:
        raise ValueError("缺少回测 strategy，无法保存结果")

    normalized_run_id = _normalize_run_id(run_id) if run_id is not None else uuid4().hex
    normalized_created_at = _normalize_created_at(created_at) if created_at is not None else result_store_now()

    with get_result_store_connection(db_path=db_path) as conn:
        conn.execute(
            """
            INSERT INTO backtest_runs (
                run_id,
                created_at,
                symbol,
                strategy,
                request_payload,
                summary_json,
                trades_json,
                equity_curve_json,
                price_bars_json,
                chart_overlays_json,
                run_context_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_run_id,
                normalized_created_at,
                symbol,
                strategy,
                _dump_json(request),
                _dump_json(summary),
                _dump_json(trades),
                _dump_json(equity_curve),
                _dump_json(price_bars),
                _dump_json(chart_overlays),
                _dump_json(run_context),
            ),
        )
        conn.commit()

    return {
        "run_id": normalized_run_id,
        "created_at": normalized_created_at,
        "symbol": symbol,
        "strategy": strategy,
    }


def list_backtest_runs(
    *,
    page: int = 1,
    page_size: int = 20,
    symbol: str | None = None,
    strategy: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db_path: Path | None = None,
) -> dict[str, object]:
    """分页查询历史回测结果。"""

    normalized_page = _normalize_page(page)
    normalized_page_size = _normalize_page_size(page_size)
    normalized_symbol = str(symbol or "").strip().upper() or None
    normalized_strategy = str(strategy or "").strip() or None
    normalized_date_from = _normalize_date(date_from) if date_from is not None else None
    normalized_date_to = _normalize_date(date_to) if date_to is not None else None
    if normalized_date_from and normalized_date_to and normalized_date_from > normalized_date_to:
        raise ValueError("date_from 不能晚于 date_to")

    where_clauses: list[str] = []
    params: list[object] = []
    if normalized_symbol is not None:
        where_clauses.append("symbol = ?")
        params.append(normalized_symbol)
    if normalized_strategy is not None:
        where_clauses.append("strategy = ?")
        params.append(normalized_strategy)
    if normalized_date_from is not None:
        where_clauses.append("substr(created_at, 1, 10) >= ?")
        params.append(normalized_date_from)
    if normalized_date_to is not None:
        where_clauses.append("substr(created_at, 1, 10) <= ?")
        params.append(normalized_date_to)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    offset = (normalized_page - 1) * normalized_page_size

    with get_result_store_connection(db_path=db_path) as conn:
        total = int(
            conn.execute(
                f"SELECT COUNT(*) AS count FROM backtest_runs {where_sql}",
                params,
            ).fetchone()["count"]
        )
        rows = conn.execute(
            f"""
            SELECT run_id, created_at, symbol, strategy, request_payload, summary_json, run_context_json
            FROM backtest_runs
            {where_sql}
            ORDER BY created_at DESC, run_id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, normalized_page_size, offset],
        ).fetchall()

    return {
        "items": [_deserialize_history_row(row) for row in rows],
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "total_pages": ceil(total / normalized_page_size) if total else 0,
        "filters": {
            "symbol": normalized_symbol,
            "strategy": normalized_strategy,
            "date_from": normalized_date_from,
            "date_to": normalized_date_to,
        },
    }


def get_backtest_run(run_id: str, *, db_path: Path | None = None) -> dict[str, object]:
    """读取单条历史回测详情。"""

    normalized_run_id = _normalize_run_id(run_id)
    with get_result_store_connection(db_path=db_path) as conn:
        row = conn.execute(
            "SELECT * FROM backtest_runs WHERE run_id = ?",
            (normalized_run_id,),
        ).fetchone()

    if row is None:
        raise LookupError(f"未找到回测记录 {normalized_run_id}")
    return _deserialize_detail_row(row)


def delete_backtest_run(run_id: str, *, db_path: Path | None = None) -> dict[str, object]:
    """删除单条历史回测记录。"""

    normalized_run_id = _normalize_run_id(run_id)
    with get_result_store_connection(db_path=db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM backtest_runs WHERE run_id = ?",
            (normalized_run_id,),
        )
        conn.commit()

    if cursor.rowcount <= 0:
        raise LookupError(f"未找到回测记录 {normalized_run_id}")
    return {
        "run_id": normalized_run_id,
        "deleted": True,
    }


def compare_backtest_runs(
    run_ids: Iterable[str],
    *,
    db_path: Path | None = None,
) -> dict[str, object]:
    """读取多条历史回测并生成对比载荷。"""

    normalized_ids = _normalize_run_ids(run_ids)
    if len(normalized_ids) < 2 or len(normalized_ids) > 3:
        raise ValueError("ids 需要传 2-3 个不同的 run_id")

    placeholders = ", ".join("?" for _ in normalized_ids)
    with get_result_store_connection(db_path=db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM backtest_runs WHERE run_id IN ({placeholders})",
            normalized_ids,
        ).fetchall()

    row_map = {str(row["run_id"]): row for row in rows}
    missing = [run_id for run_id in normalized_ids if run_id not in row_map]
    if missing:
        raise LookupError(f"未找到回测记录: {', '.join(missing)}")

    details = [_deserialize_detail_row(row_map[run_id]) for run_id in normalized_ids]
    metrics = _build_compare_metrics(details)
    param_rows, all_keys, changed_keys = _build_param_diff_rows(details)

    return {
        "items": [
            {
                "run_id": item["run_id"],
                "created_at": item["created_at"],
                "symbol": item["symbol"],
                "strategy": item["strategy"],
                "asset_type": (
                    item["run_context"].get("asset_type")
                    or item["request_payload"].get("asset_type")
                    or "stock"
                ),
                "start_date": item["request_payload"].get("start_date"),
                "end_date": item["request_payload"].get("end_date"),
                "summary": item["summary"],
                "request_payload": item["request_payload"],
            }
            for item in details
        ],
        "metrics": metrics,
        "largest_spread_metric": next(
            (item["key"] for item in metrics if item.get("is_largest_spread")),
            None,
        ),
        "equity_curves": [
            {
                "run_id": item["run_id"],
                "label": _build_compare_label(item),
                "equity_curve": item["equity_curve"],
            }
            for item in details
        ],
        "param_diffs": {
            "rows": param_rows,
            "all_keys": all_keys,
            "changed_keys": changed_keys,
        },
    }


def _build_compare_metrics(items: list[dict[str, object]]) -> list[dict[str, object]]:
    metrics: list[dict[str, object]] = []
    for key, label in _SUMMARY_COMPARE_METRICS:
        values = [
            {
                "run_id": str(item["run_id"]),
                "value": dict(item.get("summary") or {}).get(key),
            }
            for item in items
        ]
        if all(entry["value"] is None for entry in values):
            continue

        numeric_values = [
            (entry["run_id"], float(entry["value"]))
            for entry in values
            if isinstance(entry["value"], (int, float)) and not isinstance(entry["value"], bool)
        ]
        spread = None
        max_run_id = None
        min_run_id = None
        if len(numeric_values) >= 2:
            min_run_id, min_value = min(numeric_values, key=lambda item: item[1])
            max_run_id, max_value = max(numeric_values, key=lambda item: item[1])
            spread = round(max_value - min_value, 6)

        metrics.append(
            {
                "key": key,
                "label": label,
                "values": values,
                "spread": spread,
                "max_run_id": max_run_id,
                "min_run_id": min_run_id,
            }
        )

    metrics.sort(
        key=lambda item: (
            item["spread"] is None,
            -(item["spread"] or 0.0),
            item["key"],
        )
    )
    largest_key = next((item["key"] for item in metrics if item["spread"] is not None), None)
    for item in metrics:
        item["is_largest_spread"] = item["key"] == largest_key
    return metrics


def _build_param_diff_rows(items: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[str], list[str]]:
    flattened_payloads = [_flatten_mapping(dict(item.get("request_payload") or {})) for item in items]
    all_keys = sorted({key for payload in flattened_payloads for key in payload})
    rows: list[dict[str, object]] = []
    changed_keys: list[str] = []

    for key in all_keys:
        values = [
            {
                "run_id": str(item["run_id"]),
                "value": payload.get(key),
            }
            for item, payload in zip(items, flattened_payloads, strict=True)
        ]
        serialized_values = [
            json.dumps(entry["value"], ensure_ascii=False, sort_keys=True)
            for entry in values
        ]
        is_different = len(set(serialized_values)) > 1
        if is_different:
            changed_keys.append(key)
        rows.append(
            {
                "key": key,
                "values": values,
                "is_different": is_different,
            }
        )

    rows.sort(key=lambda item: (not item["is_different"], item["key"]))
    return rows, all_keys, changed_keys


def _build_compare_label(item: dict[str, object]) -> str:
    summary = dict(item.get("summary") or {})
    final_equity = summary.get("final_equity")
    final_text = f"{final_equity:.2f}" if isinstance(final_equity, (int, float)) else "--"
    return f"{item['symbol']} · {item['strategy']} · {final_text}"


def _deserialize_history_row(row: sqlite3.Row) -> dict[str, object]:
    request_payload = _load_json(row["request_payload"], {})
    summary = _load_json(row["summary_json"], {})
    run_context = _load_json(row["run_context_json"], {})
    asset_type = (
        run_context.get("asset_type")
        or request_payload.get("asset_type")
        or "stock"
    )
    return {
        "run_id": row["run_id"],
        "created_at": row["created_at"],
        "symbol": row["symbol"],
        "strategy": row["strategy"],
        "asset_type": asset_type,
        "start_date": request_payload.get("start_date"),
        "end_date": request_payload.get("end_date"),
        "params": request_payload.get("params") or {},
        "request_payload": request_payload,
        "summary": summary,
    }


def _deserialize_detail_row(row: sqlite3.Row) -> dict[str, object]:
    request_payload = _load_json(row["request_payload"], {})
    summary = _load_json(row["summary_json"], {})
    trades = _load_json(row["trades_json"], [])
    equity_curve = _load_json(row["equity_curve_json"], [])
    price_bars = _load_json(row["price_bars_json"], [])
    chart_overlays = _load_json(row["chart_overlays_json"], {})
    run_context = _load_json(row["run_context_json"], {})
    if "symbol" not in run_context:
        run_context["symbol"] = row["symbol"]
    if "strategy" not in run_context:
        run_context["strategy"] = row["strategy"]
    return {
        "run_id": row["run_id"],
        "created_at": row["created_at"],
        "symbol": row["symbol"],
        "strategy": row["strategy"],
        "request_payload": request_payload,
        "summary": summary,
        "trades": trades,
        "equity_curve": equity_curve,
        "price_bars": price_bars,
        "chart_overlays": chart_overlays,
        "run_context": run_context,
    }


def _flatten_mapping(value: dict[str, object], prefix: str = "") -> dict[str, object]:
    flattened: dict[str, object] = {}
    for key in sorted(value):
        path = f"{prefix}.{key}" if prefix else str(key)
        item = value[key]
        if isinstance(item, dict):
            flattened.update(_flatten_mapping(dict(item), path))
            continue
        flattened[path] = item
    return flattened


def _normalize_page(value: int) -> int:
    page = int(value)
    if page < 1:
        raise ValueError("page 必须 >= 1")
    return page


def _normalize_page_size(value: int) -> int:
    page_size = int(value)
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size 必须在 1-100 之间")
    return page_size


def _normalize_run_id(value: str) -> str:
    run_id = str(value or "").strip()
    if not run_id:
        raise ValueError("run_id 不能为空")
    return run_id


def _normalize_run_ids(values: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        run_id = _normalize_run_id(value)
        if run_id in seen:
            continue
        normalized.append(run_id)
        seen.add(run_id)
    return normalized


def _normalize_created_at(value: str) -> str:
    return datetime.fromisoformat(str(value)).isoformat(timespec="seconds")


def _normalize_date(value: str) -> str:
    return datetime.fromisoformat(str(value)).date().isoformat()


def _dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _load_json(raw: str | None, default: Any) -> Any:
    if raw in (None, ""):
        return default
    return json.loads(raw)


__all__ = [
    "compare_backtest_runs",
    "delete_backtest_run",
    "ensure_result_store_schema",
    "get_backtest_run",
    "get_result_store_connection",
    "list_backtest_runs",
    "result_store_now",
    "save_backtest_run",
]
