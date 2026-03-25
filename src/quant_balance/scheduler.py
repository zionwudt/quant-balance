"""盘后自动扫描调度器。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from email.message import EmailMessage
import json
import logging
from pathlib import Path
import smtplib
import sqlite3
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4
from zoneinfo import ZoneInfo

from quant_balance.core.strategies import SIGNAL_REGISTRY
from quant_balance.data.common import CACHE_DB_PATH, DataLoadError, load_app_config, load_tushare_token
from quant_balance.logging_utils import get_logger, log_event
from quant_balance.services.screening_service import run_stock_screening

logger = get_logger(__name__)

SCHEDULER_TIMEZONE = ZoneInfo("Asia/Shanghai")
DEFAULT_SCAN_TIME = "16:00"
DEFAULT_LOOKBACK_DAYS = 365
DEFAULT_TOP_N = 20
DEFAULT_CASH = 100_000.0

_CREATE_SCAN_RUNS_SQL = """
CREATE TABLE IF NOT EXISTS signal_scans (
    scan_id TEXT PRIMARY KEY,
    requested_trade_date TEXT NOT NULL,
    effective_trade_date TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    scheduled INTEGER NOT NULL DEFAULT 0,
    forced INTEGER NOT NULL DEFAULT 0,
    is_trade_day INTEGER,
    status TEXT NOT NULL,
    signals_count INTEGER NOT NULL DEFAULT 0,
    strategies_json TEXT NOT NULL,
    notifications_json TEXT NOT NULL,
    message TEXT
);
"""

_CREATE_SIGNALS_SQL = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    strategy TEXT NOT NULL,
    symbol TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    side TEXT NOT NULL,
    rank INTEGER,
    score REAL,
    total_return REAL,
    sharpe_ratio REAL,
    max_drawdown REAL,
    total_trades INTEGER,
    win_rate REAL,
    profit_factor REAL,
    final_value REAL,
    source TEXT NOT NULL,
    raw_payload TEXT NOT NULL
);
"""

_CREATE_SIGNALS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_signals_trade_date
ON signals (trade_date, strategy, generated_at DESC);
"""


@dataclass(slots=True)
class SchedulerConfig:
    enabled: bool = False
    scan_time: str = DEFAULT_SCAN_TIME
    strategies: list[str] = field(default_factory=lambda: ["macd", "rsi"])
    symbols_source: str = "stock_pool"
    symbols: list[str] = field(default_factory=list)
    asset_type: str = "stock"
    top_n: int = DEFAULT_TOP_N
    lookback_days: int = DEFAULT_LOOKBACK_DAYS
    cash: float = DEFAULT_CASH
    data_provider: str | None = None
    pool_filters: dict[str, object] = field(default_factory=dict)
    signal_params: dict[str, dict[str, object]] = field(default_factory=dict)


@dataclass(slots=True)
class ScanSignal:
    scan_id: str
    trade_date: str
    generated_at: str
    strategy: str
    symbol: str
    asset_type: str
    side: str
    rank: int
    score: float | None
    total_return: float | None
    sharpe_ratio: float | None
    max_drawdown: float | None
    total_trades: int | None
    win_rate: float | None
    profit_factor: float | None
    final_value: float | None
    source: str = "scheduler"
    raw_payload: dict[str, object] = field(default_factory=dict)


class DailyScanScheduler:
    """APScheduler 封装。"""

    def __init__(
        self,
        *,
        config_loader: callable | None = None,
        db_path: Path | None = None,
    ) -> None:
        self._config_loader = config_loader or load_app_config
        self.db_path = db_path or CACHE_DB_PATH
        self._scheduler = None
        self._started = False
        self._last_scan = None
        self._apscheduler_available = None

    def start(self) -> bool:
        """按配置启动后台调度器。"""

        config = load_scheduler_config(self._config_loader())
        if not config.enabled:
            self._started = False
            return False

        scheduler_cls, trigger_cls = _load_apscheduler()
        self._apscheduler_available = scheduler_cls is not None
        if scheduler_cls is None or trigger_cls is None:
            log_event(
                logger,
                "SCHEDULER_DISABLED",
                level=logging.WARNING,
                reason="apscheduler_missing",
            )
            self._started = False
            return False

        if self._scheduler is not None:
            return self._started

        hour, minute = parse_scan_time(config.scan_time)
        self._scheduler = scheduler_cls(timezone=str(SCHEDULER_TIMEZONE))
        self._scheduler.add_job(
            self.run_scheduled_scan,
            trigger=trigger_cls(day_of_week="mon-fri", hour=hour, minute=minute),
            id="daily_scan",
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=3600,
        )
        self._scheduler.start()
        self._started = True
        log_event(
            logger,
            "SCHEDULER_STARTED",
            scan_time=config.scan_time,
            strategies=config.strategies,
            symbols_source=config.symbols_source,
        )
        return True

    def shutdown(self) -> None:
        """关闭后台调度器。"""

        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
        self._started = False

    def run_scheduled_scan(self) -> dict[str, object]:
        """由 APScheduler 定时触发。"""

        result = run_daily_scan(
            scheduled=True,
            force=False,
            config=self._config_loader(),
            db_path=self.db_path,
        )
        self._last_scan = result
        return result

    def run_manual_scan(self, *, trade_date: str | None = None, force: bool = True) -> dict[str, object]:
        """手动触发一次盘后扫描。"""

        result = run_daily_scan(
            trade_date=trade_date,
            scheduled=False,
            force=force,
            config=self._config_loader(),
            db_path=self.db_path,
        )
        self._last_scan = result
        return result

    def get_status(self) -> dict[str, object]:
        """返回调度器状态。"""

        config = load_scheduler_config(self._config_loader())
        job = self._scheduler.get_job("daily_scan") if self._scheduler is not None else None
        if self._apscheduler_available is None:
            scheduler_cls, _ = _load_apscheduler()
            self._apscheduler_available = scheduler_cls is not None
        last_scan = self._last_scan
        if last_scan is None:
            try:
                last_scan = load_last_scan_record(db_path=self.db_path)
            except sqlite3.Error:
                last_scan = None

        return {
            "enabled": config.enabled,
            "running": bool(self._started and self._scheduler is not None),
            "apscheduler_available": self._apscheduler_available,
            "config": asdict(config),
            "next_run_time": job.next_run_time.isoformat() if job and job.next_run_time else None,
            "last_scan": last_scan,
        }


def load_scheduler_config(config: dict[str, object] | None = None) -> SchedulerConfig:
    """从 TOML 配置解析调度器设置。"""

    app_config = config or load_app_config()
    raw = dict(app_config.get("scheduler") or {})

    strategies = [str(item).strip() for item in raw.get("strategies", ["macd", "rsi"]) if str(item).strip()]
    if not strategies:
        raise ValueError("scheduler.strategies 不能为空。")
    unknown = [name for name in strategies if name not in SIGNAL_REGISTRY]
    if unknown:
        raise ValueError(f"scheduler.strategies 存在未知信号: {unknown}")

    symbols_source = str(raw.get("symbols_source", "stock_pool")).strip().lower()
    if symbols_source not in {"stock_pool", "manual"}:
        raise ValueError("scheduler.symbols_source 仅支持 stock_pool / manual")

    symbols = [str(item).strip().upper() for item in raw.get("symbols", []) if str(item).strip()]
    if symbols_source == "manual" and not symbols:
        raise ValueError("scheduler.symbols_source=manual 时必须提供 scheduler.symbols")

    asset_type = str(raw.get("asset_type", "stock")).strip()
    if asset_type not in {"stock", "convertible_bond"}:
        raise ValueError("scheduler.asset_type 仅支持 stock / convertible_bond")
    if asset_type == "convertible_bond" and symbols_source != "manual":
        raise ValueError("可转债定时扫描当前仅支持 symbols_source=manual")

    scan_time = str(raw.get("scan_time", DEFAULT_SCAN_TIME)).strip()
    parse_scan_time(scan_time)

    pool_filters = dict(raw.get("pool_filters") or {})
    signal_params = {
        str(name): dict(params or {})
        for name, params in dict(raw.get("signal_params") or {}).items()
    }

    return SchedulerConfig(
        enabled=bool(raw.get("enabled", False)),
        scan_time=scan_time,
        strategies=strategies,
        symbols_source=symbols_source,
        symbols=symbols,
        asset_type=asset_type,
        top_n=max(1, int(raw.get("top_n", DEFAULT_TOP_N))),
        lookback_days=max(30, int(raw.get("lookback_days", DEFAULT_LOOKBACK_DAYS))),
        cash=float(raw.get("cash", DEFAULT_CASH)),
        data_provider=raw.get("data_provider"),
        pool_filters=pool_filters,
        signal_params=signal_params,
    )


def parse_scan_time(value: str) -> tuple[int, int]:
    """解析 HH:MM 扫描时间。"""

    text = str(value).strip()
    if len(text) != 5 or text[2] != ":":
        raise ValueError("scheduler.scan_time 必须是 HH:MM 格式")
    hour_text, minute_text = text.split(":", 1)
    hour = int(hour_text)
    minute = int(minute_text)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("scheduler.scan_time 超出有效时间范围")
    return hour, minute


def run_daily_scan(
    *,
    trade_date: str | None = None,
    scheduled: bool = False,
    force: bool = False,
    config: dict[str, object] | None = None,
    db_path: Path | None = None,
) -> dict[str, object]:
    """执行一次盘后策略扫描。"""

    scheduler_config = load_scheduler_config(config)
    requested_trade_date = normalize_trade_date(trade_date or current_shanghai_date().isoformat())
    started_at = shanghai_now()
    scan_id = build_scan_id(requested_trade_date)
    notifications: list[dict[str, object]] = []
    effective_trade_date: str | None = None

    try:
        effective_trade_date, is_trade_day = resolve_scan_trade_date(
            requested_trade_date,
            force=force,
        )
        if not is_trade_day and not force:
            payload = {
                "scan_id": scan_id,
                "requested_trade_date": requested_trade_date,
                "effective_trade_date": effective_trade_date,
                "scheduled": scheduled,
                "forced": force,
                "status": "skipped",
                "is_trade_day": False,
                "signals_count": 0,
                "strategies": scheduler_config.strategies,
                "strategy_runs": [],
                "signals": [],
                "notifications": [],
                "started_at": started_at.isoformat(),
                "completed_at": shanghai_now().isoformat(),
                "message": "非交易日，已跳过自动扫描。",
            }
            persist_scan_record(payload, db_path=db_path)
            return payload

        lookback_start = (
            datetime.fromisoformat(effective_trade_date) - timedelta(days=scheduler_config.lookback_days)
        ).date().isoformat()
        generated_at = shanghai_now().isoformat()
        signals: list[ScanSignal] = []
        strategy_runs: list[dict[str, object]] = []

        for strategy in scheduler_config.strategies:
            signal_params = dict(scheduler_config.signal_params.get(strategy) or {})
            result = run_stock_screening(
                pool_date=effective_trade_date,
                start_date=lookback_start,
                end_date=effective_trade_date,
                asset_type=scheduler_config.asset_type,
                signal=strategy,
                signal_params=signal_params,
                top_n=scheduler_config.top_n,
                cash=scheduler_config.cash,
                symbols=scheduler_config.symbols if scheduler_config.symbols_source == "manual" else None,
                pool_filters=scheduler_config.pool_filters if scheduler_config.symbols_source == "stock_pool" else None,
                data_provider=scheduler_config.data_provider,
            )
            strategy_signals = build_scan_signals(
                scan_id=scan_id,
                trade_date=effective_trade_date,
                generated_at=generated_at,
                strategy=strategy,
                asset_type=scheduler_config.asset_type,
                rankings=result.get("rankings") or [],
            )
            signals.extend(strategy_signals)
            strategy_runs.append({
                "strategy": strategy,
                "ranked_count": len(result.get("rankings") or []),
                "total_screened": result.get("total_screened", 0),
                "run_context": result.get("run_context", {}),
            })

        persist_scan_signals(
            scan_id=scan_id,
            trade_date=effective_trade_date,
            strategies=scheduler_config.strategies,
            signals=signals,
            db_path=db_path,
        )
        notifications = send_scan_notifications(
            trade_date=effective_trade_date,
            strategy_runs=strategy_runs,
            signals=signals,
            config=config,
        )

        payload = {
            "scan_id": scan_id,
            "requested_trade_date": requested_trade_date,
            "effective_trade_date": effective_trade_date,
            "scheduled": scheduled,
            "forced": force,
            "status": "completed",
            "is_trade_day": True,
            "signals_count": len(signals),
            "strategies": scheduler_config.strategies,
            "strategy_runs": strategy_runs,
            "signals": [serialize_signal(item) for item in signals],
            "notifications": notifications,
            "started_at": started_at.isoformat(),
            "completed_at": shanghai_now().isoformat(),
            "message": "盘后扫描完成。",
        }
        persist_scan_record(payload, db_path=db_path)
        log_event(
            logger,
            "DAILY_SCAN_RUN",
            scan_id=scan_id,
            requested_trade_date=requested_trade_date,
            effective_trade_date=effective_trade_date,
            scheduled=scheduled,
            forced=force,
            strategies=scheduler_config.strategies,
            signals_count=len(signals),
            notifications_count=len(notifications),
            status="completed",
        )
        return payload
    except Exception as exc:  # noqa: BLE001
        payload = {
            "scan_id": scan_id,
            "requested_trade_date": requested_trade_date,
            "effective_trade_date": effective_trade_date,
            "scheduled": scheduled,
            "forced": force,
            "status": "failed",
            "is_trade_day": None,
            "signals_count": 0,
            "strategies": scheduler_config.strategies,
            "strategy_runs": [],
            "signals": [],
            "notifications": notifications,
            "started_at": started_at.isoformat(),
            "completed_at": shanghai_now().isoformat(),
            "message": str(exc),
        }
        persist_scan_record(payload, db_path=db_path)
        log_event(
            logger,
            "DAILY_SCAN_RUN",
            level=logging.ERROR,
            exc_info=True,
            scan_id=scan_id,
            requested_trade_date=requested_trade_date,
            effective_trade_date=effective_trade_date,
            scheduled=scheduled,
            forced=force,
            strategies=scheduler_config.strategies,
            status="failed",
            detail=str(exc),
        )
        raise


def build_scan_signals(
    *,
    scan_id: str,
    trade_date: str,
    generated_at: str,
    strategy: str,
    asset_type: str,
    rankings: list[dict[str, object]],
) -> list[ScanSignal]:
    """把筛选排名结果转换成可持久化 Signal。"""

    signals: list[ScanSignal] = []
    for index, item in enumerate(rankings, start=1):
        signals.append(
            ScanSignal(
                scan_id=scan_id,
                trade_date=trade_date,
                generated_at=generated_at,
                strategy=strategy,
                symbol=str(item.get("symbol", "")).upper(),
                asset_type=asset_type,
                side="buy",
                rank=index,
                score=_pick_signal_score(item),
                total_return=_optional_float(item.get("total_return")),
                sharpe_ratio=_optional_float(item.get("sharpe_ratio")),
                max_drawdown=_optional_float(item.get("max_drawdown")),
                total_trades=_optional_int(item.get("total_trades")),
                win_rate=_optional_float(item.get("win_rate")),
                profit_factor=_optional_float(item.get("profit_factor")),
                final_value=_optional_float(item.get("final_value")),
                raw_payload=dict(item),
            )
        )
    return signals


def list_recent_signals(
    *,
    limit: int = 20,
    trade_date: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, object]]:
    """读取最近持久化的信号列表。"""

    limit = max(1, min(int(limit), 200))
    query = (
        "SELECT id, scan_id, trade_date, generated_at, strategy, symbol, asset_type, side, rank, score, "
        "total_return, sharpe_ratio, max_drawdown, total_trades, win_rate, profit_factor, final_value, source, raw_payload "
        "FROM signals "
    )
    params: list[object] = []
    if trade_date:
        query += "WHERE trade_date = ? "
        params.append(normalize_trade_date(trade_date))
    query += "ORDER BY generated_at DESC, id DESC LIMIT ?"
    params.append(limit)

    with get_scheduler_connection(db_path=db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [deserialize_signal_row(row) for row in rows]


def load_last_scan_record(*, db_path: Path | None = None) -> dict[str, object] | None:
    """读取最近一次扫描记录。"""

    with get_scheduler_connection(db_path=db_path) as conn:
        row = conn.execute(
            "SELECT scan_id, requested_trade_date, effective_trade_date, started_at, completed_at, scheduled, forced, "
            "is_trade_day, status, signals_count, strategies_json, notifications_json, message "
            "FROM signal_scans ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    return {
        "scan_id": row["scan_id"],
        "requested_trade_date": row["requested_trade_date"],
        "effective_trade_date": row["effective_trade_date"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "scheduled": bool(row["scheduled"]),
        "forced": bool(row["forced"]),
        "is_trade_day": None if row["is_trade_day"] is None else bool(row["is_trade_day"]),
        "status": row["status"],
        "signals_count": row["signals_count"],
        "strategies": json.loads(row["strategies_json"] or "[]"),
        "notifications": json.loads(row["notifications_json"] or "[]"),
        "message": row["message"],
    }


def get_scheduler_connection(*, db_path: Path | None = None) -> sqlite3.Connection:
    """获取调度器 SQLite 连接。"""

    path = db_path or CACHE_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_SCAN_RUNS_SQL)
    conn.execute(_CREATE_SIGNALS_SQL)
    conn.execute(_CREATE_SIGNALS_INDEX_SQL)
    return conn


def persist_scan_record(payload: dict[str, object], *, db_path: Path | None = None) -> None:
    """保存扫描执行记录。"""

    with get_scheduler_connection(db_path=db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO signal_scans "
            "(scan_id, requested_trade_date, effective_trade_date, started_at, completed_at, scheduled, forced, "
            "is_trade_day, status, signals_count, strategies_json, notifications_json, message) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                payload["scan_id"],
                payload["requested_trade_date"],
                payload.get("effective_trade_date"),
                payload["started_at"],
                payload.get("completed_at"),
                1 if payload.get("scheduled") else 0,
                1 if payload.get("forced") else 0,
                None if payload.get("is_trade_day") is None else (1 if payload.get("is_trade_day") else 0),
                payload["status"],
                int(payload.get("signals_count", 0)),
                json.dumps(payload.get("strategies") or [], ensure_ascii=False),
                json.dumps(payload.get("notifications") or [], ensure_ascii=False),
                str(payload.get("message") or ""),
            ),
        )
        conn.commit()


def persist_scan_signals(
    *,
    scan_id: str,
    trade_date: str,
    strategies: list[str],
    signals: list[ScanSignal],
    db_path: Path | None = None,
) -> None:
    """持久化一次扫描生成的信号。"""

    with get_scheduler_connection(db_path=db_path) as conn:
        placeholders = ", ".join("?" for _ in strategies)
        conn.execute(
            f"DELETE FROM signals WHERE trade_date = ? AND strategy IN ({placeholders}) AND source = ?",
            [trade_date, *strategies, "scheduler"],
        )
        conn.executemany(
            "INSERT INTO signals "
            "(scan_id, trade_date, generated_at, strategy, symbol, asset_type, side, rank, score, total_return, "
            "sharpe_ratio, max_drawdown, total_trades, win_rate, profit_factor, final_value, source, raw_payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    item.scan_id,
                    item.trade_date,
                    item.generated_at,
                    item.strategy,
                    item.symbol,
                    item.asset_type,
                    item.side,
                    item.rank,
                    item.score,
                    item.total_return,
                    item.sharpe_ratio,
                    item.max_drawdown,
                    item.total_trades,
                    item.win_rate,
                    item.profit_factor,
                    item.final_value,
                    item.source,
                    json.dumps(item.raw_payload, ensure_ascii=False, sort_keys=True),
                )
                for item in signals
            ],
        )
        conn.commit()


def resolve_scan_trade_date(trade_date: str, *, force: bool = False) -> tuple[str, bool]:
    """解析调度扫描应使用的交易日。"""

    normalized = normalize_trade_date(trade_date)
    if is_trade_day(normalized):
        return normalized, True
    if not force:
        return normalized, False
    previous = get_previous_trade_day(normalized)
    return previous, False


def is_trade_day(trade_date: str) -> bool:
    """判断某日是否为交易日。"""

    dates = query_trade_calendar(trade_date, trade_date)
    return any(item["is_open"] and item["trade_date"] == trade_date for item in dates)


def get_previous_trade_day(trade_date: str) -> str:
    """返回指定日期之前最近一个交易日。"""

    target = datetime.fromisoformat(normalize_trade_date(trade_date)).date()
    rows = query_trade_calendar(
        (target - timedelta(days=31)).isoformat(),
        target.isoformat(),
    )
    open_dates = [item["trade_date"] for item in rows if item["is_open"] and item["trade_date"] <= target.isoformat()]
    if not open_dates:
        raise DataLoadError("无法从 Tushare trade_cal 获取最近交易日。")
    return open_dates[-1]


def query_trade_calendar(start_date: str, end_date: str) -> list[dict[str, object]]:
    """查询交易日历。"""

    normalized_start = normalize_trade_date(start_date)
    normalized_end = normalize_trade_date(end_date)

    try:
        import tushare as ts
    except ImportError as exc:  # pragma: no cover - 依赖缺失时由调用方处理
        raise DataLoadError("当前环境未安装 tushare，无法查询 trade_cal。") from exc

    try:
        pro = ts.pro_api(load_tushare_token())
        frame = pro.trade_cal(
            exchange="",
            start_date=normalized_start.replace("-", ""),
            end_date=normalized_end.replace("-", ""),
        )
    except Exception as exc:  # noqa: BLE001
        raise DataLoadError(f"查询 Tushare trade_cal 失败：{exc}") from exc

    if frame is None or frame.empty:
        return []

    records: list[dict[str, object]] = []
    for _, row in frame.sort_values("cal_date").iterrows():
        cal_date = str(row.get("cal_date") or "")
        if len(cal_date) != 8:
            continue
        records.append({
            "trade_date": f"{cal_date[:4]}-{cal_date[4:6]}-{cal_date[6:8]}",
            "is_open": str(row.get("is_open", "0")) == "1",
        })
    return records


def send_scan_notifications(
    *,
    trade_date: str,
    strategy_runs: list[dict[str, object]],
    signals: list[ScanSignal],
    config: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    """根据配置推送扫描结果通知。"""

    app_config = config or load_app_config()
    notify_cfg = dict(app_config.get("notifications") or {})
    title = f"QuantBalance 盘后扫描 {trade_date}"
    body = format_notification_body(trade_date=trade_date, strategy_runs=strategy_runs, signals=signals)
    results: list[dict[str, object]] = []

    if webhook := str(notify_cfg.get("wecom_webhook") or "").strip():
        results.append(_send_wecom(webhook, title=title, body=body))
    if webhook := str(notify_cfg.get("dingding_webhook") or "").strip():
        results.append(_send_dingding(webhook, title=title, body=body))
    if sendkey := str(notify_cfg.get("serverchan_sendkey") or "").strip():
        results.append(_send_serverchan(sendkey, title=title, body=body))
    if recipient := str(notify_cfg.get("email_recipient") or "").strip():
        results.append(_send_email(recipient, title=title, body=body, config=notify_cfg))

    return results


def format_notification_body(
    *,
    trade_date: str,
    strategy_runs: list[dict[str, object]],
    signals: list[ScanSignal],
) -> str:
    """构造通知正文。"""

    lines = [f"{trade_date} 盘后扫描完成，共生成 {len(signals)} 条信号。"]
    by_strategy: dict[str, list[ScanSignal]] = {}
    for signal in signals:
        by_strategy.setdefault(signal.strategy, []).append(signal)

    for run in strategy_runs:
        strategy = str(run.get("strategy") or "-")
        items = by_strategy.get(strategy, [])
        preview = ", ".join(
            f"{item.symbol}(#{item.rank}, {item.score:.2f})" if item.score is not None else f"{item.symbol}(#{item.rank})"
            for item in items[:5]
        )
        lines.append(
            f"- {strategy}: ranked={run.get('ranked_count', 0)}, total={run.get('total_screened', 0)}"
            + (f", top={preview}" if preview else "")
        )
    return "\n".join(lines)


def serialize_signal(signal: ScanSignal) -> dict[str, object]:
    payload = asdict(signal)
    payload["raw_payload"] = dict(signal.raw_payload)
    return payload


def deserialize_signal_row(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "scan_id": row["scan_id"],
        "trade_date": row["trade_date"],
        "generated_at": row["generated_at"],
        "strategy": row["strategy"],
        "symbol": row["symbol"],
        "asset_type": row["asset_type"],
        "side": row["side"],
        "rank": row["rank"],
        "score": row["score"],
        "total_return": row["total_return"],
        "sharpe_ratio": row["sharpe_ratio"],
        "max_drawdown": row["max_drawdown"],
        "total_trades": row["total_trades"],
        "win_rate": row["win_rate"],
        "profit_factor": row["profit_factor"],
        "final_value": row["final_value"],
        "source": row["source"],
        "raw_payload": json.loads(row["raw_payload"] or "{}"),
    }


def normalize_trade_date(value: str) -> str:
    return datetime.fromisoformat(str(value)).date().isoformat()


def current_shanghai_date() -> date:
    return shanghai_now().date()


def shanghai_now() -> datetime:
    return datetime.now(tz=SCHEDULER_TIMEZONE)


def build_scan_id(trade_date: str) -> str:
    return f"scan-{trade_date}-{uuid4().hex[:10]}"


def _pick_signal_score(item: dict[str, object]) -> float | None:
    for key in ("total_return", "sharpe_ratio", "final_value", "win_rate"):
        value = _optional_float(item.get(key))
        if value is not None:
            return value
    return None


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _send_wecom(webhook: str, *, title: str, body: str) -> dict[str, object]:
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": f"## {title}\n\n{body.replace(chr(10), '<br/>')}",
        },
    }
    return _post_json(channel="wecom", url=webhook, payload=payload)


def _send_dingding(webhook: str, *, title: str, body: str) -> dict[str, object]:
    payload = {
        "msgtype": "text",
        "text": {
            "content": f"{title}\n{body}",
        },
    }
    return _post_json(channel="dingding", url=webhook, payload=payload)


def _send_serverchan(sendkey: str, *, title: str, body: str) -> dict[str, object]:
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    data = urlencode({"title": title, "desp": body}).encode("utf-8")
    request = Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    return _send_request(channel="serverchan", request=request)


def _send_email(
    recipient: str,
    *,
    title: str,
    body: str,
    config: dict[str, object],
) -> dict[str, object]:
    smtp_host = str(config.get("smtp_host") or "").strip()
    sender = str(config.get("smtp_sender") or "").strip()
    if not smtp_host or not sender:
        return {
            "channel": "email",
            "status": "skipped",
            "detail": "缺少 smtp_host 或 smtp_sender 配置",
        }

    smtp_port = int(config.get("smtp_port", 465))
    username = str(config.get("smtp_username") or "").strip()
    password = str(config.get("smtp_password") or "").strip()
    use_ssl = bool(config.get("smtp_use_ssl", True))

    message = EmailMessage()
    message["Subject"] = title
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)

    try:
        smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with smtp_cls(smtp_host, smtp_port, timeout=10) as client:
            if not use_ssl and bool(config.get("smtp_starttls", True)):
                client.starttls()
            if username:
                client.login(username, password)
            client.send_message(message)
    except Exception as exc:  # noqa: BLE001
        return {
            "channel": "email",
            "status": "failed",
            "detail": str(exc),
        }
    return {
        "channel": "email",
        "status": "sent",
        "detail": recipient,
    }


def _post_json(*, channel: str, url: str, payload: dict[str, object]) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return _send_request(channel=channel, request=request)


def _send_request(*, channel: str, request: Request) -> dict[str, object]:
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        return {
            "channel": channel,
            "status": "failed",
            "detail": str(exc),
        }
    return {
        "channel": channel,
        "status": "sent",
        "detail": body[:200],
    }


def _load_apscheduler() -> tuple[type | None, type | None]:
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        return None, None
    return BackgroundScheduler, CronTrigger
