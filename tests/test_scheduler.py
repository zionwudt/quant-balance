"""测试定时调度与信号持久化。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from quant_balance.scheduler import (
    DailyScanScheduler,
    list_recent_signals,
    load_last_scan_record,
    parse_scan_time,
    resolve_scan_trade_date,
    run_daily_scan,
)


def test_parse_scan_time_accepts_hh_mm():
    assert parse_scan_time("16:00") == (16, 0)


def test_resolve_scan_trade_date_uses_previous_trade_day_when_forced():
    with (
        patch("quant_balance.scheduler.is_trade_day", return_value=False),
        patch("quant_balance.scheduler.get_previous_trade_day", return_value="2024-03-29"),
    ):
        trade_date, is_trade_day = resolve_scan_trade_date("2024-03-30", force=True)

    assert trade_date == "2024-03-29"
    assert is_trade_day is False


def test_run_daily_scan_skips_non_trade_day(tmp_path: Path):
    config = {
        "scheduler": {
            "strategies": ["macd"],
            "symbols_source": "manual",
            "symbols": ["AAA"],
        },
    }
    db_path = tmp_path / "scheduler.db"

    with patch("quant_balance.scheduler.resolve_scan_trade_date", return_value=("2024-03-30", False)):
        payload = run_daily_scan(
            trade_date="2024-03-30",
            force=False,
            config=config,
            db_path=db_path,
        )

    assert payload["status"] == "skipped"
    assert payload["signals_count"] == 0
    assert load_last_scan_record(db_path=db_path)["status"] == "skipped"


def test_run_daily_scan_persists_signals_and_notifications(tmp_path: Path):
    config = {
        "scheduler": {
            "strategies": ["macd", "rsi"],
            "symbols_source": "manual",
            "symbols": ["AAA", "BBB"],
            "top_n": 2,
        },
    }
    db_path = tmp_path / "scheduler.db"
    macd_result = {
        "rankings": [
            {"symbol": "AAA", "total_return": 0.18, "sharpe_ratio": 1.4, "total_trades": 3},
            {"symbol": "BBB", "total_return": 0.12, "sharpe_ratio": 1.1, "total_trades": 2},
        ],
        "total_screened": 2,
        "run_context": {"signal": "macd"},
    }
    rsi_result = {
        "rankings": [
            {"symbol": "CCC", "total_return": 0.08, "sharpe_ratio": 0.9, "total_trades": 1},
        ],
        "total_screened": 2,
        "run_context": {"signal": "rsi"},
    }

    with (
        patch("quant_balance.scheduler.resolve_scan_trade_date", return_value=("2024-03-29", True)),
        patch("quant_balance.scheduler.run_stock_screening", side_effect=[macd_result, rsi_result]),
        patch(
            "quant_balance.scheduler.send_scan_notifications",
            return_value=[{"channel": "wecom", "status": "sent"}],
        ),
    ):
        payload = run_daily_scan(
            trade_date="2024-03-29",
            force=True,
            config=config,
            db_path=db_path,
        )

    assert payload["status"] == "completed"
    assert payload["signals_count"] == 3
    assert payload["notifications"][0]["status"] == "sent"

    items = list_recent_signals(limit=10, db_path=db_path)
    assert len(items) == 3
    assert items[0]["source"] == "scheduler"
    assert {item["strategy"] for item in items} == {"macd", "rsi"}

    last_scan = load_last_scan_record(db_path=db_path)
    assert last_scan["status"] == "completed"
    assert last_scan["signals_count"] == 3


def test_daily_scan_scheduler_start_and_manual_run(tmp_path: Path):
    config = {
        "scheduler": {
            "enabled": True,
            "scan_time": "16:05",
            "strategies": ["macd"],
            "symbols_source": "manual",
            "symbols": ["AAA"],
        },
    }

    class FakeJob:
        next_run_time = datetime(2024, 3, 29, 16, 5)

    class FakeScheduler:
        def __init__(self, timezone: str):
            self.timezone = timezone
            self.running = False
            self.job = FakeJob()

        def add_job(self, func, trigger, id, replace_existing, coalesce, misfire_grace_time):  # noqa: ANN001
            self.func = func
            self.trigger = trigger
            self.id = id

        def start(self):
            self.running = True

        def shutdown(self, wait: bool = False):  # noqa: FBT001, ARG002
            self.running = False

        def get_job(self, job_id: str):  # noqa: ARG002
            return self.job

    class FakeTrigger:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    scheduler = DailyScanScheduler(config_loader=lambda: config, db_path=tmp_path / "scheduler.db")

    with patch("quant_balance.scheduler._load_apscheduler", return_value=(FakeScheduler, FakeTrigger)):
        assert scheduler.start() is True
        status = scheduler.get_status()

    assert status["running"] is True
    assert status["next_run_time"] == "2024-03-29T16:05:00"

    with patch("quant_balance.scheduler.run_daily_scan", return_value={"scan_id": "scan-1"}) as mock_run:
        payload = scheduler.run_manual_scan(force=True)

    assert payload == {"scan_id": "scan-1"}
    mock_run.assert_called_once()

    scheduler.shutdown()
