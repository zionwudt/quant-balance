"""测试信号导出格式。"""

from __future__ import annotations

import ast
import json
from datetime import datetime
from pathlib import Path

from quant_balance.core.signals import Signal, persist_signals
from quant_balance.execution.signal_export import export_signals_for_date


def _seed_signals(db_path: Path) -> None:
    persist_signals(
        [
            Signal(
                symbol="600519.SH",
                name="贵州茅台",
                side="BUY",
                strategy="macd",
                reason="DIF上穿DEA",
                price=1680.0,
                suggested_qty=100,
                timestamp=datetime.fromisoformat("2024-12-23T15:01:00+08:00"),
                trade_date="2024-12-23",
            ),
            Signal(
                symbol="000001.SZ",
                name="平安银行",
                side="SELL",
                strategy="rsi",
                reason="RSI跌破阈值",
                price=10.5,
                suggested_qty=200,
                timestamp=datetime.fromisoformat("2024-12-23T15:05:00+08:00"),
                trade_date="2024-12-23",
            ),
        ],
        db_path=db_path,
    )


def test_export_signals_csv_uses_gbk_encoding(tmp_path: Path) -> None:
    db_path = tmp_path / "signals.db"
    _seed_signals(db_path)

    artifact = export_signals_for_date(format="csv", date="2024-12-23", db_path=db_path)

    assert artifact.filename == "signals-2024-12-23.csv"
    assert artifact.format == "csv"
    text = artifact.content.decode("gbk")
    assert "代码,方向,数量,价格,策略,原因" in text
    assert "600519.SH,BUY,100,1680.00,MACD,DIF上穿DEA" in text
    assert "000001.SZ,SELL,200,10.50,RSI,RSI跌破阈值" in text


def test_export_signals_json_contains_full_signal_items(tmp_path: Path) -> None:
    db_path = tmp_path / "signals.db"
    _seed_signals(db_path)

    artifact = export_signals_for_date(format="json", date="2024-12-23", db_path=db_path)

    assert artifact.filename == "signals-2024-12-23.json"
    payload = json.loads(artifact.content.decode("utf-8"))
    assert payload["date"] == "2024-12-23"
    assert payload["total"] == 2
    assert payload["items"][0]["symbol"] == "000001.SZ"
    assert payload["items"][1]["symbol"] == "600519.SH"
    assert payload["items"][1]["trigger_reason"] == "DIF上穿DEA"


def test_export_signals_qmt_generates_valid_python_script(tmp_path: Path) -> None:
    db_path = tmp_path / "signals.db"
    _seed_signals(db_path)

    artifact = export_signals_for_date(format="qmt", date="2024-12-23", db_path=db_path)
    script = artifact.content.decode("utf-8")

    assert artifact.filename == "signals-2024-12-23-qmt.py"
    assert "from xtquant import xtconstant, xttrader" in script
    assert "from xtquant.xttype import StockAccount" in script
    assert 'ACCOUNT_ID = "YOUR_ACCOUNT_ID"' in script
    assert '"symbol": "600519.SH"' in script
    assert '"side": "BUY"' in script
    ast.parse(script)


def test_export_signals_rejects_unknown_format(tmp_path: Path) -> None:
    db_path = tmp_path / "signals.db"
    _seed_signals(db_path)

    try:
        export_signals_for_date(format="xml", date="2024-12-23", db_path=db_path)
    except ValueError as exc:
        assert "不支持的导出格式" in str(exc)
    else:
        raise AssertionError("expected ValueError")
