"""测试模拟盘会话与信号撮合。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

from quant_balance.core.signals import Signal, persist_signals
from quant_balance.execution.paper_trading import PaperTradingManager

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _sample_df() -> pd.DataFrame:
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    return pd.DataFrame(
        {
            "Open": [10.0, 10.5, 11.0, 11.2],
            "High": [10.2, 10.9, 11.6, 11.4],
            "Low": [9.8, 10.3, 10.8, 10.9],
            "Close": [10.0, 10.8, 11.5, 11.1],
            "Volume": [1_000_000, 1_100_000, 1_050_000, 900_000],
        },
        index=dates,
    )


def _seed_signals(db_path: Path) -> None:
    persist_signals(
        [
            Signal(
                symbol="600519.SH",
                name="贵州茅台",
                side="BUY",
                strategy="macd",
                reason="首个买入信号",
                price=10.0,
                suggested_qty=100,
                timestamp=datetime(2024, 1, 2, 15, 0, tzinfo=SHANGHAI),
                trade_date="2024-01-02",
            ),
            Signal(
                symbol="600519.SH",
                name="贵州茅台",
                side="SELL",
                strategy="macd",
                reason="卖出离场",
                price=10.8,
                suggested_qty=100,
                timestamp=datetime(2024, 1, 3, 15, 0, tzinfo=SHANGHAI),
                trade_date="2024-01-03",
            ),
        ],
        db_path=db_path,
    )


def test_paper_status_executes_signals_on_next_open_and_marks_to_market(tmp_path: Path) -> None:
    db_path = tmp_path / "paper.db"
    _seed_signals(db_path)
    frame = _sample_df()

    with patch("quant_balance.execution.paper_trading.load_dataframe", return_value=frame):
        manager = PaperTradingManager(db_path=db_path)
        manager.start_session(
            strategy="macd",
            strategy_params={"fast_period": 12},
            symbols=["600519.SH"],
            initial_cash=100_000.0,
            start_date="2024-01-02",
        )

        status = manager.get_status(as_of_date="2024-01-03")

    assert status["has_session"] is True
    assert status["status"] == "running"
    assert len(status["trades"]) == 1
    assert status["trades"][0]["trade_date"] == "2024-01-03"
    assert status["trades"][0]["price"] == 10.5
    assert status["holdings"][0]["qty"] == 100
    assert status["holdings"][0]["last_price"] == 10.8
    assert status["summary"]["cash"] == 98_950.0
    assert status["summary"]["holdings_value"] == 1_080.0
    assert status["summary"]["equity"] == 100_030.0
    assert status["equity_curve"][-1]["date"] == "2024-01-03"
    assert status["equity_curve"][-1]["equity"] == 100_030.0


def test_pause_blocks_new_signal_execution_but_keeps_mark_to_market(tmp_path: Path) -> None:
    db_path = tmp_path / "paper.db"
    _seed_signals(db_path)
    frame = _sample_df()

    with patch("quant_balance.execution.paper_trading.load_dataframe", return_value=frame):
        manager = PaperTradingManager(db_path=db_path)
        started = manager.start_session(
            strategy="macd",
            symbols=["600519.SH"],
            initial_cash=100_000.0,
            start_date="2024-01-02",
        )
        manager.get_status(session_id=started["session_id"], as_of_date="2024-01-03")
        paused = manager.pause_session(session_id=started["session_id"])
        status = manager.get_status(session_id=started["session_id"], as_of_date="2024-01-04")

    assert paused["status"] == "paused"
    assert status["status"] == "paused"
    assert len(status["trades"]) == 1
    assert status["holdings"][0]["last_price"] == 11.5
    assert status["summary"]["equity"] == 100_100.0


def test_stop_generates_report_and_restart_restores_running_session(tmp_path: Path) -> None:
    db_path = tmp_path / "paper.db"
    _seed_signals(db_path)
    frame = _sample_df()

    with patch("quant_balance.execution.paper_trading.load_dataframe", return_value=frame):
        first_manager = PaperTradingManager(db_path=db_path)
        started = first_manager.start_session(
            strategy="macd",
            symbols=["600519.SH"],
            initial_cash=100_000.0,
            start_date="2024-01-02",
        )

        restored = PaperTradingManager(db_path=db_path)
        running = restored.get_status(session_id=started["session_id"], as_of_date="2024-01-03")
        stopped = restored.stop_session(session_id=started["session_id"], as_of_date="2024-01-04")
        final_status = PaperTradingManager(db_path=db_path).get_status(session_id=started["session_id"])

    assert running["status"] == "running"
    assert running["session_id"] == started["session_id"]
    assert stopped["status"] == "stopped"
    assert len(stopped["trades"]) == 2
    assert stopped["summary"]["cash"] == 100_050.0
    assert stopped["summary"]["equity"] == 100_050.0
    assert stopped["summary"]["trades_count"] == 1
    assert stopped["summary"]["orders_count"] == 2
    assert stopped["summary"]["win_rate_pct"] == 100.0
    assert stopped["report"]["run_context"]["end_date"] == "2024-01-04"
    assert final_status["status"] == "stopped"
    assert final_status["summary"]["equity"] == 100_050.0
