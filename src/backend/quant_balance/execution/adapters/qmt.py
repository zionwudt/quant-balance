"""QMT 执行适配器实现。

支持两种模式：
1. 注入模式：外部传入 order_executor/positions_provider/balance_provider
2. miniQMT 模式：自动连接 miniQMT 进程（需安装 xtquant SDK）

miniQMT 使用说明：
- 安装 xtquant: pip install xtquant（或从 QMT 客户端目录复制）
- 配置 qmt_path 指向 QMT 安装目录
- 确保 miniQMT 进程已启动
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from quant_balance.execution.adapters.base import BrokerAdapter
from quant_balance.execution.models import BrokerBalance, BrokerPosition, ExecutionSignal, OrderResult


class QmtAdapter(BrokerAdapter):
    """QMT / miniQMT 适配器骨架。"""

    def __init__(
        self,
        *,
        account_id: str = "",
        account_type: str = "STOCK",
        qmt_path: str = "",
        session_id: str = "",
        order_executor: Callable[[dict[str, object]], object] | None = None,
        positions_provider: Callable[[], Iterable[BrokerPosition | Mapping[str, object]]] | None = None,
        balance_provider: Callable[[], BrokerBalance | Mapping[str, object]] | None = None,
    ) -> None:
        super().__init__(adapter_name="qmt")
        self.account_id = str(account_id or "").strip()
        self.account_type = str(account_type or "STOCK").strip().upper() or "STOCK"
        self.qmt_path = str(qmt_path or "").strip()
        self.session_id = str(session_id or "").strip()
        self._order_executor = order_executor
        self._positions_provider = positions_provider
        self._balance_provider = balance_provider
        self._xt_trader = None
        self._xt_connected = False

    def connect(self) -> bool:
        """尝试连接 miniQMT。成功返回 True，未安装 xtquant 返回 False。"""
        if self._xt_connected:
            return True
        try:
            from xtquant.xttrader import XtQuantTrader
            from xtquant.xttype import StockAccount
        except ImportError:
            return False

        if not self.qmt_path:
            raise RuntimeError("QMT 适配器需要配置 qmt_path。")

        self._xt_trader = XtQuantTrader(self.qmt_path, self.session_id or "quant_balance")
        account = StockAccount(self.account_id, self.account_type)
        self._xt_trader.start()
        connect_result = self._xt_trader.connect()
        if connect_result != 0:
            raise RuntimeError(f"miniQMT 连接失败，错误码: {connect_result}")
        self._xt_connected = True
        return True

    def place_order(self, signal: ExecutionSignal | Mapping[str, object]) -> OrderResult:
        normalized = self.normalize_signal(signal)
        payload = self.build_order_payload(normalized)
        if self._order_executor is None:
            raise RuntimeError("QMT 适配器尚未配置下单执行器。")

        result = self._order_executor(payload)
        order_id, status, message = _parse_execution_result(result)
        return OrderResult(
            order_id=order_id,
            symbol=normalized.symbol,
            side=normalized.side,
            quantity=normalized.quantity,
            filled_quantity=normalized.quantity if status == "filled" else 0,
            avg_price=normalized.price,
            status=status,
            adapter=self.adapter_name,
            message=message,
            raw_payload=payload,
        )

    def query_positions(self) -> list[BrokerPosition]:
        if self._positions_provider is None:
            raise RuntimeError("QMT 适配器尚未配置持仓查询提供器。")

        items: list[BrokerPosition] = []
        for entry in self._positions_provider():
            items.append(_coerce_position(entry, adapter=self.adapter_name))
        items.sort(key=lambda item: item.symbol)
        return items

    def query_balance(self) -> BrokerBalance:
        if self._balance_provider is None:
            raise RuntimeError("QMT 适配器尚未配置资金查询提供器。")

        payload = self._balance_provider()
        return _coerce_balance(payload, adapter=self.adapter_name)

    def build_order_payload(self, signal: ExecutionSignal | Mapping[str, object]) -> dict[str, object]:
        normalized = self.normalize_signal(signal)
        return {
            "account_id": self.account_id,
            "account_type": self.account_type,
            "qmt_path": self.qmt_path,
            "session_id": self.session_id,
            **self.build_signal_payload(normalized),
        }

    @staticmethod
    def build_signal_payload(signal: ExecutionSignal | Mapping[str, object]) -> dict[str, object]:
        normalized = signal if isinstance(signal, ExecutionSignal) else ExecutionSignal.from_signal_payload(signal)
        price = float(normalized.price or 0.0)
        return {
            "symbol": normalized.symbol,
            "name": normalized.name,
            "side": normalized.side,
            "quantity": normalized.quantity,
            "price": price,
            "price_type": "FIX_PRICE" if normalized.price is not None else "LATEST_PRICE",
            "strategy": normalized.strategy,
            "strategy_name": normalized.strategy.upper(),
            "reason": normalized.reason,
            "remark": _truncate_remark(
                f"{normalized.strategy.upper()} | {normalized.reason}".strip(" |")
            ),
            "signal_id": normalized.signal_id,
            "trade_date": normalized.trade_date,
            "asset_type": normalized.asset_type,
            "status": normalized.metadata.get("status", "pending"),
            "generated_at": normalized.metadata.get("generated_at"),
            "metadata": dict(normalized.metadata),
        }


def _parse_execution_result(result: object) -> tuple[str, str, str | None]:
    if isinstance(result, OrderResult):
        return result.order_id, result.status, result.message
    if isinstance(result, Mapping):
        order_id = str(result.get("order_id") or result.get("id") or result.get("order_no") or "")
        if not order_id:
            order_id = "qmt-submitted"
        status = str(result.get("status") or "submitted").strip().lower()
        if status not in {"submitted", "filled", "rejected"}:
            status = "submitted"
        message = str(result.get("message") or result.get("detail") or "").strip() or None
        return order_id, status, message
    if result in (None, ""):
        return "qmt-submitted", "submitted", None
    return str(result), "submitted", None


def _coerce_position(value: BrokerPosition | Mapping[str, object], *, adapter: str) -> BrokerPosition:
    if isinstance(value, BrokerPosition):
        payload = value
        payload.adapter = payload.adapter or adapter
        return payload
    data = dict(value or {})
    return BrokerPosition(
        symbol=str(data.get("symbol") or data.get("stock_code") or ""),
        name=str(data.get("name") or data.get("stock_name") or data.get("symbol") or ""),
        quantity=int(data.get("quantity") or data.get("qty") or data.get("volume") or 0),
        available_quantity=int(
            data.get("available_quantity")
            or data.get("available_qty")
            or data.get("can_use_volume")
            or data.get("quantity")
            or 0
        ),
        avg_price=float(data.get("avg_price") or data.get("cost_price") or data.get("open_price") or 0.0),
        market_price=float(data.get("market_price") or data.get("last_price") or data.get("price") or 0.0),
        market_value=float(data.get("market_value") or data.get("value") or 0.0) or None,
        unrealized_pnl=_optional_float(data.get("unrealized_pnl") or data.get("floating_profit")),
        unrealized_pnl_pct=_optional_float(data.get("unrealized_pnl_pct") or data.get("profit_ratio")),
        asset_type=str(data.get("asset_type") or "stock"),
        adapter=adapter,
    )


def _coerce_balance(value: BrokerBalance | Mapping[str, object], *, adapter: str) -> BrokerBalance:
    if isinstance(value, BrokerBalance):
        payload = value
        payload.adapter = payload.adapter or adapter
        return payload
    data = dict(value or {})
    cash = _first_number(data, "cash", "available_cash", "enable_balance")
    available_cash = _first_number(data, "available_cash", "enable_balance", "cash")
    frozen_cash = _first_number(data, "frozen_cash", "frozen_balance", default=0.0)
    market_value = _first_number(data, "market_value", "position_value", default=0.0)
    total_equity = _first_number(data, "total_equity", "asset_balance", default=cash + market_value)
    return BrokerBalance(
        cash=cash,
        available_cash=available_cash,
        frozen_cash=frozen_cash,
        market_value=market_value,
        total_equity=total_equity,
        currency=str(data.get("currency") or "CNY"),
        adapter=adapter,
    )


def _first_number(data: Mapping[str, object], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        value = data.get(key)
        if value in (None, ""):
            continue
        return float(value)
    return float(default)


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _truncate_remark(value: str, limit: int = 120) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


__all__ = ["QmtAdapter"]
