"""默认手工执行适配器。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_balance.execution.adapters.base import BrokerAdapter
from quant_balance.execution.models import BrokerBalance, BrokerPosition, ExecutionSignal, OrderResult


class ManualAdapter(BrokerAdapter):
    """内存态手工执行适配器，可作为默认落地方案。"""

    def __init__(self, *, initial_cash: float = 100_000.0, currency: str = "CNY") -> None:
        super().__init__(adapter_name="manual")
        self._cash = round(float(initial_cash), 6)
        if self._cash < 0:
            raise ValueError("initial_cash 不能小于 0。")
        self._currency = str(currency or "CNY").strip().upper() or "CNY"
        self._positions: dict[str, dict[str, Any]] = {}
        self._order_seq = 0

    def place_order(self, signal: ExecutionSignal | Mapping[str, object]) -> OrderResult:
        normalized = self.normalize_signal(signal)
        if normalized.price is None:
            return self._reject_order(normalized, "ManualAdapter 需要显式价格。")

        self._order_seq += 1
        order_id = f"manual-{self._order_seq:06d}"
        notional = normalized.price * normalized.quantity
        existing = self._positions.get(normalized.symbol)

        if normalized.side == "BUY":
            if self._cash + 1e-9 < notional:
                return self._reject_order(normalized, "可用现金不足。", order_id=order_id)
            self._cash = round(self._cash - notional, 6)
            if existing is None:
                self._positions[normalized.symbol] = {
                    "symbol": normalized.symbol,
                    "name": normalized.name,
                    "quantity": normalized.quantity,
                    "avg_price": normalized.price,
                    "market_price": normalized.price,
                    "asset_type": normalized.asset_type,
                }
            else:
                total_qty = int(existing["quantity"]) + normalized.quantity
                total_cost = float(existing["avg_price"]) * int(existing["quantity"]) + notional
                existing["quantity"] = total_qty
                existing["avg_price"] = total_cost / total_qty if total_qty > 0 else normalized.price
                existing["market_price"] = normalized.price
                existing["name"] = normalized.name or existing["name"]
            return OrderResult(
                order_id=order_id,
                symbol=normalized.symbol,
                side=normalized.side,
                quantity=normalized.quantity,
                filled_quantity=normalized.quantity,
                avg_price=normalized.price,
                status="filled",
                adapter=self.adapter_name,
                message="ManualAdapter 已记录为手工成交。",
                raw_payload=_raw_signal_payload(normalized),
            )

        if existing is None or int(existing["quantity"]) < normalized.quantity:
            return self._reject_order(normalized, "可卖数量不足。", order_id=order_id)

        self._cash = round(self._cash + notional, 6)
        remaining = int(existing["quantity"]) - normalized.quantity
        if remaining > 0:
            existing["quantity"] = remaining
            existing["market_price"] = normalized.price
        else:
            self._positions.pop(normalized.symbol, None)
        return OrderResult(
            order_id=order_id,
            symbol=normalized.symbol,
            side=normalized.side,
            quantity=normalized.quantity,
            filled_quantity=normalized.quantity,
            avg_price=normalized.price,
            status="filled",
            adapter=self.adapter_name,
            message="ManualAdapter 已记录为手工成交。",
            raw_payload=_raw_signal_payload(normalized),
        )

    def query_positions(self) -> list[BrokerPosition]:
        items = [
            BrokerPosition(
                symbol=str(payload["symbol"]),
                name=str(payload["name"]),
                quantity=int(payload["quantity"]),
                available_quantity=int(payload["quantity"]),
                avg_price=float(payload["avg_price"]),
                market_price=float(payload.get("market_price") or payload["avg_price"]),
                asset_type=str(payload.get("asset_type") or "stock"),
                adapter=self.adapter_name,
            )
            for payload in self._positions.values()
            if int(payload["quantity"]) > 0
        ]
        items.sort(key=lambda item: item.symbol)
        return items

    def query_balance(self) -> BrokerBalance:
        positions = self.query_positions()
        market_value = round(sum(float(item.market_value or 0.0) for item in positions), 6)
        return BrokerBalance(
            cash=self._cash,
            available_cash=self._cash,
            frozen_cash=0.0,
            market_value=market_value,
            total_equity=round(self._cash + market_value, 6),
            currency=self._currency,
            adapter=self.adapter_name,
        )

    def _reject_order(
        self,
        signal: ExecutionSignal,
        message: str,
        *,
        order_id: str | None = None,
    ) -> OrderResult:
        return OrderResult(
            order_id=order_id or f"manual-rejected-{self._order_seq + 1:06d}",
            symbol=signal.symbol,
            side=signal.side,
            quantity=signal.quantity,
            filled_quantity=0,
            avg_price=signal.price,
            status="rejected",
            adapter=self.adapter_name,
            message=message,
            raw_payload=_raw_signal_payload(signal),
        )


def _raw_signal_payload(signal: ExecutionSignal) -> dict[str, Any]:
    return {
        "symbol": signal.symbol,
        "side": signal.side,
        "quantity": signal.quantity,
        "price": signal.price,
        "name": signal.name,
        "strategy": signal.strategy,
        "reason": signal.reason,
        "asset_type": signal.asset_type,
        "signal_id": signal.signal_id,
        "trade_date": signal.trade_date,
        "metadata": dict(signal.metadata),
    }


__all__ = ["ManualAdapter"]
