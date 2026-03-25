"""测试信号对象、存储与查询。"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import sqlite3

import pandas as pd

from quant_balance.core import signals as signal_store
from quant_balance.core.signals import (
    Signal,
    get_signal_connection,
    list_recent_signals,
    list_signal_history,
    list_today_signals,
    persist_signals,
    update_signal_status,
)


def _make_tracking_df() -> pd.DataFrame:
    dates = pd.date_range("2024-03-29", periods=30, freq="B")
    close = [10.0 + index * 0.5 for index in range(len(dates))]
    return pd.DataFrame({
        "Open": close,
        "High": close,
        "Low": close,
        "Close": close,
        "Volume": [1_000_000] * len(dates),
    }, index=dates)


def test_signal_history_computes_tracking_returns(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "signals.db"
    signal = Signal(
        symbol="AAA",
        name="测试股A",
        side="BUY",
        strategy="macd",
        reason="MACD 金叉",
        price=10.0,
        suggested_qty=100,
        timestamp=datetime.fromisoformat("2024-03-29T16:00:00+08:00"),
        trade_date="2024-03-29",
    )
    persist_signals([signal], db_path=db_path)

    monkeypatch.setattr(signal_store, "current_signal_date", lambda: date(2024, 4, 30))
    monkeypatch.setattr(signal_store, "load_dataframe", lambda *args, **kwargs: _make_tracking_df())

    history = list_signal_history(days=60, page=1, page_size=10, db_path=db_path)
    today = list_today_signals(as_of_date="2024-03-29", db_path=db_path)

    assert history["total"] == 1
    assert today["total"] == 1
    item = history["items"][0]
    assert item["symbol"] == "AAA"
    assert item["return_5d_pct"] == 25.0
    assert item["return_10d_pct"] == 50.0
    assert item["performance_20d_pct"] == 100.0
    assert item["outcome_label"] == "信号有效"


def test_update_signal_status_persists(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "signals.db"
    persist_signals(
        [
            Signal(
                symbol="AAA",
                name="测试股A",
                side="BUY",
                strategy="rsi",
                reason="RSI 超卖",
                price=10.0,
                suggested_qty=100,
                timestamp=datetime.fromisoformat("2024-03-29T16:00:00+08:00"),
                trade_date="2024-03-29",
            ),
        ],
        db_path=db_path,
    )

    monkeypatch.setattr(signal_store, "current_signal_date", lambda: date(2024, 3, 29))
    updated = update_signal_status(1, status="ignored", db_path=db_path)

    assert updated["id"] == 1
    assert updated["status"] == "ignored"
    assert updated["status_label"] == "已忽略"


def test_legacy_scheduler_signal_table_migrates(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "signals.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE signals (
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
        )
        """
    )
    conn.execute(
        "INSERT INTO signals "
        "(scan_id, trade_date, generated_at, strategy, symbol, asset_type, side, rank, score, total_return, "
        "sharpe_ratio, max_drawdown, total_trades, win_rate, profit_factor, final_value, source, raw_payload) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "scan-1",
            "2024-03-29",
            "2024-03-29T16:00:00+08:00",
            "macd",
            "AAA",
            "stock",
            "BUY",
            1,
            1.2,
            0.18,
            1.4,
            -0.05,
            3,
            0.67,
            1.8,
            118000.0,
            "scheduler",
            "{}",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(signal_store, "current_signal_date", lambda: date(2024, 3, 29))
    items = list_recent_signals(limit=10, db_path=db_path)

    assert len(items) == 1
    assert items[0]["status"] == "pending"
    assert items[0]["name"] == "AAA"
    assert items[0]["created_at"] == "2024-03-29T16:00:00+08:00"

    with get_signal_connection(db_path=db_path) as migrated:
        columns = {
            str(row["name"])
            for row in migrated.execute("PRAGMA table_info(signals)").fetchall()
        }

    assert {"name", "created_at", "status", "return_5d_pct", "tracking_updated_at"}.issubset(columns)
