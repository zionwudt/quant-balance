"""测试执行适配层模型与默认适配器。"""

from __future__ import annotations

import pytest

from quant_balance.execution import (
    BrokerBalance,
    BrokerPosition,
    ExecutionSignal,
    ManualAdapter,
    QmtAdapter,
    build_broker_adapter,
)


def test_execution_signal_from_payload_normalizes_signal_dict() -> None:
    signal = ExecutionSignal.from_signal_payload({
        "id": 12,
        "symbol": "600519.sh",
        "name": "贵州茅台",
        "side": "buy",
        "suggested_qty": 200,
        "signal_price": 1680.5,
        "strategy": "macd",
        "trigger_reason": "金叉确认",
        "trade_date": "2024-12-23T15:00:00",
        "asset_type": "stock",
        "status": "pending",
    })

    assert signal.symbol == "600519.SH"
    assert signal.side == "BUY"
    assert signal.quantity == 200
    assert signal.price == 1680.5
    assert signal.reason == "金叉确认"
    assert signal.trade_date == "2024-12-23"
    assert signal.signal_id == 12
    assert signal.metadata["status"] == "pending"


def test_manual_adapter_updates_positions_and_balance() -> None:
    adapter = ManualAdapter(initial_cash=100_000.0)

    buy_result = adapter.place_order({
        "symbol": "600519.SH",
        "name": "贵州茅台",
        "side": "BUY",
        "suggested_qty": 100,
        "signal_price": 100.0,
        "strategy": "manual",
    })
    assert buy_result.status == "filled"
    assert buy_result.filled_quantity == 100

    positions = adapter.query_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "600519.SH"
    assert positions[0].quantity == 100
    assert positions[0].market_value == 10_000.0

    balance = adapter.query_balance()
    assert balance.available_cash == 90_000.0
    assert balance.total_equity == 100_000.0

    sell_result = adapter.place_order({
        "symbol": "600519.SH",
        "name": "贵州茅台",
        "side": "SELL",
        "suggested_qty": 40,
        "signal_price": 110.0,
        "strategy": "manual",
    })
    assert sell_result.status == "filled"
    assert adapter.query_positions()[0].quantity == 60
    assert adapter.query_balance().available_cash == 94_400.0


def test_manual_adapter_rejects_invalid_execution() -> None:
    adapter = ManualAdapter(initial_cash=1_000.0)

    insufficient_cash = adapter.place_order({
        "symbol": "AAA",
        "side": "BUY",
        "suggested_qty": 100,
        "signal_price": 50.0,
    })
    assert insufficient_cash.status == "rejected"
    assert insufficient_cash.message == "可用现金不足。"

    missing_position = adapter.place_order({
        "symbol": "AAA",
        "side": "SELL",
        "suggested_qty": 100,
        "signal_price": 10.0,
    })
    assert missing_position.status == "rejected"
    assert missing_position.message == "可卖数量不足。"


def test_qmt_adapter_maps_signal_and_provider_payloads() -> None:
    qmt = QmtAdapter(
        account_id="test-account",
        account_type="stock",
        qmt_path="/tmp/qmt",
        session_id="session-1",
        order_executor=lambda payload: {"order_id": "qmt-1", "status": "submitted"},
        positions_provider=lambda: [
            {
                "stock_code": "600519.SH",
                "stock_name": "贵州茅台",
                "volume": 200,
                "can_use_volume": 180,
                "cost_price": 1650.0,
                "last_price": 1688.0,
            }
        ],
        balance_provider=lambda: {
            "enable_balance": 80_000.0,
            "asset_balance": 120_000.0,
            "position_value": 40_000.0,
        },
    )

    signal = ExecutionSignal(
        symbol="600519.SH",
        name="贵州茅台",
        side="BUY",
        quantity=100,
        price=1680.0,
        strategy="macd",
        reason="金叉确认",
        signal_id=7,
        trade_date="2024-12-23",
    )

    payload = qmt.build_order_payload(signal)
    assert payload["account_id"] == "test-account"
    assert payload["strategy_name"] == "MACD"
    assert payload["price_type"] == "FIX_PRICE"
    assert payload["remark"] == "MACD | 金叉确认"

    order_result = qmt.place_order(signal)
    assert order_result.status == "submitted"
    assert order_result.order_id == "qmt-1"

    positions = qmt.query_positions()
    assert positions[0].symbol == "600519.SH"
    assert positions[0].available_quantity == 180
    assert positions[0].market_price == 1688.0

    balance = qmt.query_balance()
    assert balance.available_cash == 80_000.0
    assert balance.market_value == 40_000.0
    assert balance.total_equity == 120_000.0


def test_qmt_adapter_requires_executor_and_providers_when_not_configured() -> None:
    qmt = QmtAdapter()
    signal = ExecutionSignal(symbol="AAA", side="BUY", quantity=100, price=10.0)

    with pytest.raises(RuntimeError, match="下单执行器"):
        qmt.place_order(signal)
    with pytest.raises(RuntimeError, match="持仓查询提供器"):
        qmt.query_positions()
    with pytest.raises(RuntimeError, match="资金查询提供器"):
        qmt.query_balance()


def test_build_broker_adapter_returns_expected_types() -> None:
    assert isinstance(build_broker_adapter("manual"), ManualAdapter)
    assert isinstance(build_broker_adapter("qmt"), QmtAdapter)

    with pytest.raises(ValueError, match="未知执行适配器"):
        build_broker_adapter("unknown")


def test_balance_and_position_models_compute_derived_fields() -> None:
    position = BrokerPosition(symbol="AAA", quantity=100, avg_price=10.0, market_price=12.0)
    balance = BrokerBalance(cash=50_000.0, available_cash=48_000.0, market_value=position.market_value or 0.0)

    assert position.market_value == 1_200.0
    assert position.unrealized_pnl == 200.0
    assert position.unrealized_pnl_pct == 20.0
    assert balance.total_equity == 51_200.0
