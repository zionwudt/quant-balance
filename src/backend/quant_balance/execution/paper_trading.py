"""模拟盘：虚拟账户持久化、信号撮合与净值跟踪。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd

from quant_balance.core.report import build_equity_performance_report
from quant_balance.core.signals import get_signal_connection, normalize_trade_date
from quant_balance.core.strategies import SIGNAL_REGISTRY
from quant_balance.data.common import CACHE_DB_PATH
from quant_balance.data.market_loader import load_dataframe

PAPER_TIMEZONE = ZoneInfo("Asia/Shanghai")
VALID_PAPER_SESSION_STATUSES = frozenset({"running", "paused", "stopped"})

_CREATE_PAPER_SESSIONS_SQL = """
CREATE TABLE IF NOT EXISTS paper_sessions (
    session_id TEXT PRIMARY KEY,
    strategy TEXT NOT NULL,
    strategy_params TEXT NOT NULL,
    initial_cash REAL NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    stopped_at TEXT,
    symbols_json TEXT NOT NULL DEFAULT '[]',
    asset_type TEXT NOT NULL DEFAULT 'stock',
    start_date TEXT NOT NULL,
    data_provider TEXT,
    report_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);
"""

_CREATE_PAPER_TRADES_SQL = """
CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    signal_id INTEGER,
    symbol TEXT NOT NULL,
    name TEXT,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    trade_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    strategy TEXT NOT NULL,
    reason TEXT,
    asset_type TEXT NOT NULL DEFAULT 'stock',
    notional REAL NOT NULL,
    realized_pnl REAL,
    realized_return_pct REAL,
    signal_payload_json TEXT NOT NULL DEFAULT '{}'
);
"""

_CREATE_PAPER_INDEXES_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_paper_sessions_status ON paper_sessions (status, updated_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_paper_trades_session_date ON paper_trades (session_id, trade_date ASC, id ASC);",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_trades_session_signal ON paper_trades (session_id, signal_id) WHERE signal_id IS NOT NULL;",
)

_PAPER_SESSION_MIGRATION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("symbols_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("asset_type", "TEXT NOT NULL DEFAULT 'stock'"),
    ("start_date", "TEXT NOT NULL DEFAULT '1970-01-01'"),
    ("data_provider", "TEXT"),
    ("report_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("updated_at", "TEXT NOT NULL DEFAULT ''"),
)

_PAPER_TRADE_MIGRATION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("signal_id", "INTEGER"),
    ("name", "TEXT"),
    ("strategy", "TEXT NOT NULL DEFAULT ''"),
    ("reason", "TEXT"),
    ("asset_type", "TEXT NOT NULL DEFAULT 'stock'"),
    ("notional", "REAL NOT NULL DEFAULT 0"),
    ("realized_pnl", "REAL"),
    ("realized_return_pct", "REAL"),
    ("signal_payload_json", "TEXT NOT NULL DEFAULT '{}'"),
)


@dataclass(slots=True)
class PaperSessionRecord:
    """模拟盘会话元数据。"""

    session_id: str
    strategy: str
    strategy_params: dict[str, object]
    symbols: list[str]
    asset_type: str
    initial_cash: float
    status: str
    start_date: str
    started_at: str
    stopped_at: str | None
    data_provider: str | None
    updated_at: str
    report: dict[str, object]


class PaperTradingManager:
    """模拟盘会话管理器。"""

    def __init__(self, *, db_path: Path | None = None) -> None:
        self.db_path = db_path or CACHE_DB_PATH
        self._active_session_id = self._find_active_session_id()

    def start_session(
        self,
        *,
        strategy: str,
        symbols: list[str],
        initial_cash: float,
        strategy_params: dict[str, object] | None = None,
        asset_type: str = "stock",
        start_date: str | None = None,
        data_provider: str | None = None,
    ) -> dict[str, object]:
        """开启新的模拟盘会话。"""

        active = self._load_session()
        if active is not None and active.status in {"running", "paused"}:
            raise ValueError(f"已有未结束的模拟盘会话 {active.session_id}，请先停止后再新建。")

        normalized_strategy = str(strategy or "").strip()
        if normalized_strategy not in SIGNAL_REGISTRY:
            raise ValueError(f"未知策略 {strategy!r}，可用: {list(SIGNAL_REGISTRY)}")

        normalized_symbols = _normalize_symbols(symbols)
        normalized_asset_type = _normalize_asset_type(asset_type)
        normalized_start_date = normalize_trade_date(start_date or paper_now().date().isoformat())
        normalized_cash = float(initial_cash)
        if normalized_cash <= 0:
            raise ValueError("initial_cash 必须大于 0。")

        session_id = uuid4().hex
        now = paper_now().isoformat()
        with get_paper_connection(db_path=self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO paper_sessions (
                    session_id,
                    strategy,
                    strategy_params,
                    initial_cash,
                    status,
                    started_at,
                    stopped_at,
                    symbols_json,
                    asset_type,
                    start_date,
                    data_provider,
                    report_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    normalized_strategy,
                    _dump_json(strategy_params or {}),
                    normalized_cash,
                    "running",
                    now,
                    None,
                    _dump_json(normalized_symbols),
                    normalized_asset_type,
                    normalized_start_date,
                    str(data_provider).strip() or None if data_provider is not None else None,
                    _dump_json({}),
                    now,
                ),
            )
            conn.commit()

        self._active_session_id = session_id
        return self.get_status(session_id=session_id, as_of_date=normalized_start_date)

    def get_status(
        self,
        *,
        session_id: str | None = None,
        as_of_date: str | None = None,
    ) -> dict[str, object]:
        """返回当前或指定会话的状态快照。"""

        session = self._load_session(session_id)
        if session is None:
            return {"has_session": False, "session_id": None}

        if session.status == "stopped" and as_of_date is None and session.report:
            payload = dict(session.report)
            payload.setdefault("has_session", True)
            payload.setdefault("session_id", session.session_id)
            return payload

        end_date = _resolve_session_end_date(session, as_of_date)
        if session.status == "running":
            self._apply_pending_signals(session, end_date)
            session = self._load_session(session.session_id) or session
        return self._build_status_payload(session, as_of_date=end_date)

    def pause_session(self, *, session_id: str | None = None) -> dict[str, object]:
        """暂停当前会话。"""

        session = self._require_session(session_id)
        if session.status == "stopped":
            raise ValueError("模拟盘会话已停止，无法再次暂停。")
        if session.status == "paused":
            return self.get_status(session_id=session.session_id)

        now = paper_now().isoformat()
        with get_paper_connection(db_path=self.db_path) as conn:
            conn.execute(
                "UPDATE paper_sessions SET status = ?, updated_at = ? WHERE session_id = ?",
                ("paused", now, session.session_id),
            )
            conn.commit()
        self._active_session_id = session.session_id
        return self.get_status(session_id=session.session_id)

    def stop_session(
        self,
        *,
        session_id: str | None = None,
        as_of_date: str | None = None,
    ) -> dict[str, object]:
        """停止会话并冻结最终报告。"""

        session = self._require_session(session_id)
        if session.status == "stopped":
            return self.get_status(session_id=session.session_id)

        end_date = _resolve_session_end_date(session, as_of_date)
        if session.status == "running":
            self._apply_pending_signals(session, end_date)
            session = self._load_session(session.session_id) or session

        payload = self._build_status_payload(session, as_of_date=end_date)
        stopped_at = paper_now().isoformat()
        payload["status"] = "stopped"
        payload["stopped_at"] = stopped_at
        payload["summary"]["status"] = "stopped"
        payload["report"]["summary"]["status"] = "stopped"

        with get_paper_connection(db_path=self.db_path) as conn:
            conn.execute(
                "UPDATE paper_sessions SET status = ?, stopped_at = ?, report_json = ?, updated_at = ? WHERE session_id = ?",
                ("stopped", stopped_at, _dump_json(payload), stopped_at, session.session_id),
            )
            conn.commit()

        if self._active_session_id == session.session_id:
            self._active_session_id = None
        return payload

    def _build_status_payload(
        self,
        session: PaperSessionRecord,
        *,
        as_of_date: str,
    ) -> dict[str, object]:
        trades = self._list_session_trades(session.session_id)
        state = _replay_session_state(
            session,
            trades,
            end_date=as_of_date,
            db_path=self.db_path,
        )
        summary = build_equity_performance_report(
            state["equity_series"],
            closed_trade_pnls=state["closed_trade_pnls"],
            closed_trade_returns_pct=state["closed_trade_returns_pct"],
            orders_count=len(trades),
            exposure_pct=state["exposure_pct"],
        )
        summary.update({
            "status": session.status,
            "equity": summary.get("final_equity"),
            "cash": _rounded_money(state["cash"]),
            "holdings_value": _rounded_money(state["holdings_value"]),
            "today_pnl": _rounded_money(state["today_pnl"]),
            "positions_count": len(state["holdings"]),
            "last_trade_date": state["last_trade_date"],
            "last_mark_date": state["last_mark_date"],
        })

        run_context = {
            "session_id": session.session_id,
            "strategy": session.strategy,
            "strategy_params": dict(session.strategy_params),
            "symbols": list(session.symbols),
            "asset_type": session.asset_type,
            "initial_cash": session.initial_cash,
            "start_date": session.start_date,
            "end_date": as_of_date,
            "data_provider": session.data_provider,
        }

        report = {
            "summary": summary,
            "trades": state["trades"],
            "equity_curve": state["equity_curve"],
            "holdings": state["holdings"],
            "run_context": run_context,
        }
        return {
            "has_session": True,
            "session_id": session.session_id,
            "status": session.status,
            "started_at": session.started_at,
            "stopped_at": session.stopped_at,
            "as_of_date": as_of_date,
            "strategy": session.strategy,
            "strategy_params": dict(session.strategy_params),
            "symbols": list(session.symbols),
            "asset_type": session.asset_type,
            "initial_cash": session.initial_cash,
            "summary": summary,
            "holdings": state["holdings"],
            "trades": state["trades"],
            "equity_curve": state["equity_curve"],
            "report": report,
        }

    def _apply_pending_signals(self, session: PaperSessionRecord, as_of_date: str) -> None:
        signals = self._list_session_signals(session, as_of_date=as_of_date)
        if not signals:
            return

        existing_trades = self._list_session_trades(session.session_id)
        executed_signal_ids = {
            int(item["signal_id"])
            for item in existing_trades
            if item.get("signal_id") is not None
        }
        cash, positions = _replay_cash_and_positions(session, existing_trades)
        market = _PaperMarketDataCache(
            symbols=session.symbols,
            start_date=session.start_date,
            end_date=as_of_date,
            asset_type=session.asset_type,
            data_provider=session.data_provider,
            db_path=self.db_path,
        )

        rows: list[tuple[object, ...]] = []
        created_at = paper_now().isoformat()
        for signal in signals:
            signal_id = int(signal["id"])
            if signal_id in executed_signal_ids:
                continue

            execution = market.execution_open(signal["symbol"], signal["trade_date"])
            if execution is None:
                continue

            execution_date, execution_price = execution
            if execution_date > as_of_date:
                continue

            quantity = int(signal["suggested_qty"] or 0)
            if quantity <= 0:
                continue

            side = str(signal["side"])
            symbol = str(signal["symbol"])
            position = positions.get(symbol)
            realized_pnl = None
            realized_return_pct = None

            if side == "BUY":
                notional = execution_price * quantity
                if cash + 1e-9 < notional:
                    continue
                cash = _rounded_money(cash - notional)
                if position is None:
                    positions[symbol] = {
                        "symbol": symbol,
                        "name": signal["name"],
                        "qty": quantity,
                        "cost_price": execution_price,
                        "strategy": session.strategy,
                        "opened_at": execution_date,
                    }
                else:
                    total_qty = int(position["qty"]) + quantity
                    total_cost = float(position["cost_price"]) * int(position["qty"]) + notional
                    position["qty"] = total_qty
                    position["cost_price"] = total_cost / total_qty if total_qty > 0 else execution_price
            else:
                if position is None or int(position["qty"]) <= 0:
                    continue
                quantity = min(quantity, int(position["qty"]))
                if quantity <= 0:
                    continue
                notional = execution_price * quantity
                cost_price = float(position["cost_price"])
                realized_pnl = (execution_price - cost_price) * quantity
                realized_return_pct = ((execution_price / cost_price - 1) * 100) if cost_price > 0 else None
                cash = _rounded_money(cash + notional)
                remaining = int(position["qty"]) - quantity
                if remaining > 0:
                    position["qty"] = remaining
                else:
                    positions.pop(symbol, None)

            rows.append((
                session.session_id,
                signal_id,
                symbol,
                signal["name"],
                side,
                quantity,
                execution_price,
                execution_date,
                created_at,
                session.strategy,
                signal["reason"],
                session.asset_type,
                _rounded_money(execution_price * quantity),
                _rounded_nullable(realized_pnl),
                _rounded_nullable(realized_return_pct),
                _dump_json(signal),
            ))
            executed_signal_ids.add(signal_id)

        if not rows:
            return

        with get_paper_connection(db_path=self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO paper_trades (
                    session_id,
                    signal_id,
                    symbol,
                    name,
                    side,
                    quantity,
                    price,
                    trade_date,
                    created_at,
                    strategy,
                    reason,
                    asset_type,
                    notional,
                    realized_pnl,
                    realized_return_pct,
                    signal_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.execute(
                "UPDATE paper_sessions SET updated_at = ? WHERE session_id = ?",
                (created_at, session.session_id),
            )
            conn.commit()

    def _list_session_signals(self, session: PaperSessionRecord, *, as_of_date: str) -> list[dict[str, object]]:
        placeholders = ", ".join("?" for _ in session.symbols)
        with get_signal_connection(db_path=self.db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT id, symbol, name, side, strategy, reason, suggested_qty, trade_date
                FROM signals
                WHERE strategy = ?
                  AND asset_type = ?
                  AND trade_date >= ?
                  AND trade_date <= ?
                  AND symbol IN ({placeholders})
                ORDER BY trade_date ASC, id ASC
                """,
                [
                    session.strategy,
                    session.asset_type,
                    session.start_date,
                    as_of_date,
                    *session.symbols,
                ],
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "symbol": str(row["symbol"] or "").upper(),
                "name": str(row["name"] or row["symbol"] or "").strip() or str(row["symbol"] or "").upper(),
                "side": str(row["side"] or "BUY").strip().upper(),
                "strategy": str(row["strategy"] or "").strip(),
                "reason": str(row["reason"] or row["strategy"] or "").strip(),
                "suggested_qty": int(row["suggested_qty"] or 0),
                "trade_date": normalize_trade_date(str(row["trade_date"] or "")),
            }
            for row in rows
        ]

    def _list_session_trades(self, session_id: str) -> list[dict[str, object]]:
        with get_paper_connection(db_path=self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM paper_trades WHERE session_id = ? ORDER BY trade_date ASC, id ASC",
                (session_id,),
            ).fetchall()
        return [_deserialize_trade_row(row) for row in rows]

    def _require_session(self, session_id: str | None) -> PaperSessionRecord:
        session = self._load_session(session_id)
        if session is None:
            raise LookupError("当前没有可用的模拟盘会话。")
        return session

    def _load_session(self, session_id: str | None = None) -> PaperSessionRecord | None:
        resolved_id = (str(session_id).strip() or None) if session_id is not None else None
        with get_paper_connection(db_path=self.db_path) as conn:
            if resolved_id:
                row = conn.execute(
                    "SELECT * FROM paper_sessions WHERE session_id = ?",
                    (resolved_id,),
                ).fetchone()
            else:
                current_id = self._active_session_id or self._find_default_session_id(conn)
                row = None
                if current_id:
                    row = conn.execute(
                        "SELECT * FROM paper_sessions WHERE session_id = ?",
                        (current_id,),
                    ).fetchone()
                if row is None:
                    row = conn.execute(
                        """
                        SELECT * FROM paper_sessions
                        ORDER BY
                            CASE status
                                WHEN 'running' THEN 0
                                WHEN 'paused' THEN 1
                                ELSE 2
                            END,
                            updated_at DESC,
                            started_at DESC
                        LIMIT 1
                        """
                    ).fetchone()

        if row is None:
            return None
        session = _deserialize_session_row(row)
        if session.status in {"running", "paused"}:
            self._active_session_id = session.session_id
        return session

    def _find_active_session_id(self) -> str | None:
        path = self.db_path
        if not path.exists():
            return None

        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(str(path))
            conn.row_factory = sqlite3.Row
            has_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'paper_sessions' LIMIT 1"
            ).fetchone()
            if has_table is None:
                return None
            return self._find_default_session_id(conn, active_only=True)
        except sqlite3.Error:
            return None
        finally:
            if conn is not None:
                conn.close()

    def _find_default_session_id(self, conn: sqlite3.Connection, *, active_only: bool = False) -> str | None:
        if active_only:
            row = conn.execute(
                """
                SELECT session_id FROM paper_sessions
                WHERE status IN ('running', 'paused')
                ORDER BY updated_at DESC, started_at DESC
                LIMIT 1
                """
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT session_id FROM paper_sessions
                ORDER BY
                    CASE status
                        WHEN 'running' THEN 0
                        WHEN 'paused' THEN 1
                        ELSE 2
                    END,
                    updated_at DESC,
                    started_at DESC
                LIMIT 1
                """
            ).fetchone()
        return str(row["session_id"]) if row is not None else None


class _PaperMarketDataCache:
    """按会话缓存行情，避免重复加载。"""

    def __init__(
        self,
        *,
        symbols: list[str],
        start_date: str,
        end_date: str,
        asset_type: str,
        data_provider: str | None,
        db_path: Path | None,
    ) -> None:
        self.symbols = list(symbols)
        self.start_date = start_date
        self.end_date = end_date
        self.asset_type = asset_type
        self.data_provider = data_provider
        self.db_path = db_path
        self._frames: dict[str, pd.DataFrame | None] = {}

    def frame(self, symbol: str) -> pd.DataFrame | None:
        normalized_symbol = str(symbol).strip().upper()
        if normalized_symbol not in self._frames:
            try:
                self._frames[normalized_symbol] = load_dataframe(
                    normalized_symbol,
                    self.start_date,
                    self.end_date,
                    asset_type=self.asset_type,  # type: ignore[arg-type]
                    provider=self.data_provider,
                    db_path=self.db_path,
                )
            except Exception:  # noqa: BLE001
                self._frames[normalized_symbol] = None
        return self._frames[normalized_symbol]

    def execution_open(self, symbol: str, signal_date: str) -> tuple[str, float] | None:
        frame = self.frame(symbol)
        if frame is None or frame.empty or "Open" not in frame:
            return None
        index = frame.index
        position = int(index.searchsorted(pd.Timestamp(signal_date), side="right"))
        if position >= len(index):
            return None
        row = frame.iloc[position]
        return row.name.date().isoformat(), float(row["Open"])

    def close_price(self, symbol: str, trade_date: str) -> float | None:
        frame = self.frame(symbol)
        if frame is None or frame.empty or "Close" not in frame:
            return None
        position = int(frame.index.searchsorted(pd.Timestamp(trade_date), side="right")) - 1
        if position < 0:
            return None
        return float(frame.iloc[position]["Close"])

    def trading_dates(self) -> list[str]:
        dates: set[str] = set()
        for symbol in self.symbols:
            frame = self.frame(symbol)
            if frame is None or frame.empty:
                continue
            dates.update(idx.date().isoformat() for idx in frame.index)
        if not dates:
            return [
                item.date().isoformat()
                for item in pd.date_range(self.start_date, self.end_date, freq="B")
            ] or [self.end_date]
        dates.add(self.start_date)
        dates.add(self.end_date)
        return sorted(dates)

    def build_close_dict(self) -> dict[str, dict[str, float]]:
        """预构建 {symbol: {date_str: close_price}} 字典，供批量查询。"""
        result: dict[str, dict[str, float]] = {}
        for symbol in self.symbols:
            frame = self.frame(symbol)
            if frame is None or frame.empty or "Close" not in frame:
                continue
            closes: dict[str, float] = {}
            for idx, row in frame.iterrows():
                closes[idx.date().isoformat()] = float(row["Close"])
            result[symbol.upper()] = closes
        return result

    def close_price_from_dict(
        self,
        close_dict: dict[str, dict[str, float]],
        symbol: str,
        trade_date: str,
    ) -> float | None:
        """从预构建字典快速查询收盘价，回退到最近前一日。"""
        symbol_closes = close_dict.get(symbol.upper())
        if not symbol_closes:
            return None
        price = symbol_closes.get(trade_date)
        if price is not None:
            return price
        # 回退：找 <= trade_date 的最近日期
        candidates = [d for d in symbol_closes if d <= trade_date]
        if not candidates:
            return None
        return symbol_closes[max(candidates)]


def get_paper_connection(*, db_path: Path | None = None) -> sqlite3.Connection:
    """获取模拟盘 SQLite 连接并确保 schema 已就绪。"""

    path = db_path or CACHE_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    ensure_paper_schema(conn)
    return conn


def ensure_paper_schema(conn: sqlite3.Connection) -> None:
    """创建或升级模拟盘 schema。"""

    conn.execute(_CREATE_PAPER_SESSIONS_SQL)
    conn.execute(_CREATE_PAPER_TRADES_SQL)

    session_columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(paper_sessions)").fetchall()
    }
    for name, column_sql in _PAPER_SESSION_MIGRATION_COLUMNS:
        if name in session_columns:
            continue
        conn.execute(f"ALTER TABLE paper_sessions ADD COLUMN {name} {column_sql}")

    trade_columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(paper_trades)").fetchall()
    }
    for name, column_sql in _PAPER_TRADE_MIGRATION_COLUMNS:
        if name in trade_columns:
            continue
        conn.execute(f"ALTER TABLE paper_trades ADD COLUMN {name} {column_sql}")

    for sql in _CREATE_PAPER_INDEXES_SQL:
        conn.execute(sql)
    conn.execute(
        "UPDATE paper_sessions SET updated_at = COALESCE(NULLIF(updated_at, ''), started_at) "
        "WHERE updated_at IS NULL OR updated_at = ''"
    )
    conn.execute(
        "UPDATE paper_sessions SET symbols_json = COALESCE(NULLIF(symbols_json, ''), '[]') "
        "WHERE symbols_json IS NULL OR symbols_json = ''"
    )
    conn.execute(
        "UPDATE paper_sessions SET report_json = COALESCE(NULLIF(report_json, ''), '{}') "
        "WHERE report_json IS NULL OR report_json = ''"
    )
    conn.commit()


def paper_now() -> datetime:
    """返回上海时区当前时间。"""

    return datetime.now(tz=PAPER_TIMEZONE)


def _resolve_session_end_date(session: PaperSessionRecord, as_of_date: str | None) -> str:
    if as_of_date is not None:
        resolved = normalize_trade_date(as_of_date)
    elif session.status == "stopped" and session.stopped_at:
        resolved = normalize_trade_date(session.stopped_at)
    else:
        resolved = normalize_trade_date(paper_now().date().isoformat())
    if resolved < session.start_date:
        raise ValueError("模拟盘结束日期不能早于 start_date。")
    return resolved


def _replay_session_state(
    session: PaperSessionRecord,
    trades: list[dict[str, object]],
    *,
    end_date: str,
    db_path: Path | None = None,
) -> dict[str, object]:
    market = _PaperMarketDataCache(
        symbols=session.symbols,
        start_date=session.start_date,
        end_date=end_date,
        asset_type=session.asset_type,
        data_provider=session.data_provider,
        db_path=db_path,
    )
    trade_map: dict[str, list[dict[str, object]]] = {}
    for trade in trades:
        trade_map.setdefault(str(trade["trade_date"]), []).append(trade)

    cash = float(session.initial_cash)
    positions: dict[str, dict[str, object]] = {}
    closed_trade_pnls: list[float] = []
    closed_trade_returns_pct: list[float] = []
    trade_log: list[dict[str, object]] = []
    equity_curve: list[dict[str, object]] = []
    holding_values: list[float] = []
    last_trade_date: str | None = None

    dates = [date for date in market.trading_dates() if session.start_date <= date <= end_date]
    if not dates:
        dates = [end_date]

    # 预构建收盘价字典，避免逐日逐持仓查 DataFrame
    close_dict = market.build_close_dict()

    for trade_date in dates:
        for trade in trade_map.get(trade_date, []):
            cash = _apply_replayed_trade(
                cash,
                positions,
                trade,
                closed_trade_pnls=closed_trade_pnls,
                closed_trade_returns_pct=closed_trade_returns_pct,
            )
            trade_log.append({
                **trade,
                "timestamp": f"{trade_date}T09:30:00+08:00",
                "side_label": "买入" if trade["side"] == "BUY" else "卖出",
                "qty": trade["quantity"],
            })
            last_trade_date = trade_date

        holdings_value = 0.0
        for position in positions.values():
            close_price = market.close_price_from_dict(close_dict, str(position["symbol"]), trade_date)
            if close_price is None:
                close_price = float(position["cost_price"])
            market_value = close_price * int(position["qty"])
            pnl = (close_price - float(position["cost_price"])) * int(position["qty"])
            pnl_pct = None
            if float(position["cost_price"]) > 0:
                pnl_pct = (close_price / float(position["cost_price"]) - 1) * 100
            position["last_price"] = close_price
            position["market_value"] = market_value
            position["pnl"] = pnl
            position["pnl_pct"] = pnl_pct
            holdings_value += market_value

        equity = cash + holdings_value
        holding_values.append(holdings_value)
        equity_curve.append({
            "date": trade_date,
            "equity": _rounded_money(equity),
        })

    final_holdings = [
        {
            "symbol": str(item["symbol"]),
            "name": str(item["name"]),
            "qty": int(item["qty"]),
            "cost_price": _rounded_money(float(item["cost_price"])),
            "last_price": _rounded_money(float(item.get("last_price") or item["cost_price"])),
            "market_value": _rounded_money(float(item.get("market_value") or 0.0)),
            "pnl": _rounded_money(float(item.get("pnl") or 0.0)),
            "pnl_pct": _rounded_nullable(item.get("pnl_pct")),
            "strategy": str(item.get("strategy") or session.strategy),
            "opened_at": item.get("opened_at"),
        }
        for item in positions.values()
        if int(item["qty"]) > 0
    ]
    final_holdings.sort(key=lambda item: float(item["market_value"]), reverse=True)

    today_pnl = 0.0
    if len(equity_curve) >= 2:
        today_pnl = float(equity_curve[-1]["equity"]) - float(equity_curve[-2]["equity"])
    holdings_value = float(sum(item["market_value"] for item in final_holdings))
    equity_series = pd.Series(
        [float(item["equity"]) for item in equity_curve],
        index=pd.to_datetime([item["date"] for item in equity_curve]),
        dtype=float,
    )
    exposure_pct = (
        len([value for value in holding_values if value > 0]) / len(holding_values) * 100
        if holding_values
        else 0.0
    )
    return {
        "cash": cash,
        "holdings": final_holdings,
        "holdings_value": holdings_value,
        "today_pnl": today_pnl,
        "equity_curve": equity_curve,
        "equity_series": equity_series,
        "trades": sorted(trade_log, key=lambda item: (str(item["trade_date"]), int(item["id"])), reverse=True),
        "closed_trade_pnls": closed_trade_pnls,
        "closed_trade_returns_pct": closed_trade_returns_pct,
        "exposure_pct": exposure_pct,
        "last_trade_date": last_trade_date,
        "last_mark_date": equity_curve[-1]["date"] if equity_curve else end_date,
    }


def _replay_cash_and_positions(
    session: PaperSessionRecord,
    trades: list[dict[str, object]],
) -> tuple[float, dict[str, dict[str, object]]]:
    cash = float(session.initial_cash)
    positions: dict[str, dict[str, object]] = {}
    for trade in trades:
        cash = _apply_replayed_trade(
            cash,
            positions,
            trade,
            closed_trade_pnls=[],
            closed_trade_returns_pct=[],
        )
    return cash, positions


def _apply_replayed_trade(
    cash: float,
    positions: dict[str, dict[str, object]],
    trade: dict[str, object],
    *,
    closed_trade_pnls: list[float],
    closed_trade_returns_pct: list[float],
) -> float:
    symbol = str(trade["symbol"])
    quantity = int(trade["quantity"])
    price = float(trade["price"])
    name = str(trade.get("name") or symbol)

    if trade["side"] == "BUY":
        notional = price * quantity
        cash -= notional
        position = positions.get(symbol)
        if position is None:
            positions[symbol] = {
                "symbol": symbol,
                "name": name,
                "qty": quantity,
                "cost_price": price,
                "strategy": trade.get("strategy"),
                "opened_at": trade["trade_date"],
            }
            return cash

        total_qty = int(position["qty"]) + quantity
        total_cost = float(position["cost_price"]) * int(position["qty"]) + notional
        position["qty"] = total_qty
        position["cost_price"] = total_cost / total_qty if total_qty > 0 else price
        return cash

    position = positions.get(symbol)
    if position is None or int(position["qty"]) <= 0:
        return cash

    quantity = min(quantity, int(position["qty"]))
    if quantity <= 0:
        return cash

    cost_price = float(position["cost_price"])
    realized_pnl = (price - cost_price) * quantity
    realized_return_pct = ((price / cost_price - 1) * 100) if cost_price > 0 else None
    closed_trade_pnls.append(realized_pnl)
    if realized_return_pct is not None:
        closed_trade_returns_pct.append(realized_return_pct)

    cash += price * quantity
    remaining = int(position["qty"]) - quantity
    if remaining > 0:
        position["qty"] = remaining
    else:
        positions.pop(symbol, None)
    return cash


def _deserialize_session_row(row: sqlite3.Row) -> PaperSessionRecord:
    return PaperSessionRecord(
        session_id=str(row["session_id"]),
        strategy=str(row["strategy"] or ""),
        strategy_params=_load_json(row["strategy_params"], {}),
        symbols=_normalize_symbols(_load_json(row["symbols_json"], [])),
        asset_type=_normalize_asset_type(str(row["asset_type"] or "stock")),
        initial_cash=float(row["initial_cash"] or 0.0),
        status=_normalize_paper_status(str(row["status"] or "running")),
        start_date=normalize_trade_date(str(row["start_date"] or "") or str(row["started_at"])[:10]),
        started_at=str(row["started_at"] or ""),
        stopped_at=str(row["stopped_at"] or "") or None,
        data_provider=str(row["data_provider"] or "") or None,
        updated_at=str(row["updated_at"] or row["started_at"] or ""),
        report=_load_json(row["report_json"], {}),
    )


def _deserialize_trade_row(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": int(row["id"]),
        "session_id": str(row["session_id"]),
        "signal_id": int(row["signal_id"]) if row["signal_id"] is not None else None,
        "symbol": str(row["symbol"] or "").upper(),
        "name": str(row["name"] or row["symbol"] or "").strip() or str(row["symbol"] or "").upper(),
        "side": str(row["side"] or "BUY").strip().upper(),
        "quantity": int(row["quantity"] or 0),
        "price": float(row["price"] or 0.0),
        "trade_date": normalize_trade_date(str(row["trade_date"] or "")),
        "created_at": str(row["created_at"] or ""),
        "strategy": str(row["strategy"] or ""),
        "reason": str(row["reason"] or ""),
        "asset_type": str(row["asset_type"] or "stock"),
        "notional": float(row["notional"] or 0.0),
        "realized_pnl": _rounded_nullable(row["realized_pnl"]),
        "realized_return_pct": _rounded_nullable(row["realized_return_pct"]),
        "signal_payload": _load_json(row["signal_payload_json"], {}),
    }


def _normalize_symbols(values: list[str] | object) -> list[str]:
    if not isinstance(values, list):
        values = list(values or [])
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        symbol = str(item or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)
    if not normalized:
        raise ValueError("symbols 至少需要包含一个有效标的。")
    return normalized


def _normalize_asset_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in {"stock", "convertible_bond"}:
        raise ValueError("asset_type 仅支持 stock / convertible_bond")
    return normalized


def _normalize_paper_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in VALID_PAPER_SESSION_STATUSES:
        supported = ", ".join(sorted(VALID_PAPER_SESSION_STATUSES))
        raise ValueError(f"不支持的模拟盘状态 {value!r}，当前支持: {supported}")
    return normalized


def _dump_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _load_json(raw: object, default: object) -> object:
    text = str(raw or "").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def _rounded_money(value: float) -> float:
    return round(float(value), 6)


def _rounded_nullable(value: object) -> float | None:
    if value in (None, ""):
        return None
    return round(float(value), 6)


__all__ = [
    "PaperSessionRecord",
    "PaperTradingManager",
    "ensure_paper_schema",
    "get_paper_connection",
    "paper_now",
]
