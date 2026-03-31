"""执行层独立模型。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

EXECUTION_TIMEZONE = ZoneInfo("Asia/Shanghai")

ExecutionSide = Literal["BUY", "SELL", "SHORT", "COVER"]
OrderStatus = Literal["submitted", "filled", "rejected"]


def execution_now() -> datetime:
    """返回执行层统一使用的当前时间。"""

    return datetime.now(tz=EXECUTION_TIMEZONE)


def execution_now_iso() -> str:
    """返回执行层统一使用的当前时间字符串。"""

    return execution_now().isoformat(timespec="seconds")


@dataclass(slots=True)
class ExecutionSignal:
    """执行适配层使用的标准化信号。"""

    symbol: str
    side: ExecutionSide
    quantity: int
    price: float | None = None
    name: str = ""
    strategy: str = ""
    reason: str = ""
    asset_type: str = "stock"
    signal_id: int | None = None
    trade_date: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = str(self.symbol or "").strip().upper()
        if not self.symbol:
            raise ValueError("signal.symbol 不能为空。")

        side = str(self.side or "").strip().upper()
        if side not in {"BUY", "SELL", "SHORT", "COVER"}:
            raise ValueError(f"不支持的 signal.side {self.side!r}，当前支持: BUY / SELL / SHORT / COVER")
        self.side = side  # type: ignore[assignment]

        self.quantity = int(self.quantity)
        if self.quantity <= 0:
            raise ValueError("signal.quantity 必须大于 0。")

        if self.price in (None, "", 0, 0.0):
            self.price = None
        else:
            self.price = float(self.price)
            if self.price <= 0:
                raise ValueError("signal.price 必须大于 0，或留空表示市价语义。")

        self.name = str(self.name or self.symbol).strip() or self.symbol
        self.strategy = str(self.strategy or "").strip()
        self.reason = str(self.reason or "").strip()
        self.asset_type = str(self.asset_type or "stock").strip() or "stock"
        self.signal_id = None if self.signal_id in (None, "") else int(self.signal_id)
        self.trade_date = _normalize_date(self.trade_date)
        self.metadata = dict(self.metadata or {})

    @classmethod
    def from_signal_payload(cls, payload: Mapping[str, object]) -> "ExecutionSignal":
        """从 API / SQLite 信号字典构建执行信号。"""

        signal = dict(payload or {})
        return cls(
            symbol=str(signal.get("symbol") or ""),
            side=str(signal.get("side") or "BUY"),
            quantity=int(signal.get("suggested_qty") or signal.get("quantity") or 0),
            price=_optional_price(signal.get("signal_price", signal.get("price"))),
            name=str(signal.get("name") or signal.get("symbol") or ""),
            strategy=str(signal.get("strategy") or ""),
            reason=str(signal.get("trigger_reason") or signal.get("reason") or ""),
            asset_type=str(signal.get("asset_type") or "stock"),
            signal_id=signal.get("id"),
            trade_date=signal.get("trade_date"),
            metadata={
                key: value
                for key, value in signal.items()
                if key not in {
                    "id",
                    "symbol",
                    "side",
                    "suggested_qty",
                    "quantity",
                    "signal_price",
                    "price",
                    "name",
                    "strategy",
                    "trigger_reason",
                    "reason",
                    "asset_type",
                    "trade_date",
                }
            },
        )


@dataclass(slots=True)
class OrderResult:
    """执行适配器返回的标准化委托结果。"""

    order_id: str
    symbol: str
    side: ExecutionSide
    quantity: int
    filled_quantity: int
    status: OrderStatus
    adapter: str
    submitted_at: str = field(default_factory=execution_now_iso)
    avg_price: float | None = None
    message: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status in {"submitted", "filled"}


@dataclass(slots=True)
class BrokerPosition:
    """券商适配层统一持仓模型。"""

    symbol: str
    quantity: int
    avg_price: float
    name: str = ""
    available_quantity: int | None = None
    market_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pnl_pct: float | None = None
    asset_type: str = "stock"
    adapter: str = ""
    updated_at: str = field(default_factory=execution_now_iso)

    def __post_init__(self) -> None:
        self.symbol = str(self.symbol or "").strip().upper()
        self.quantity = int(self.quantity)
        self.avg_price = float(self.avg_price)
        self.name = str(self.name or self.symbol).strip() or self.symbol
        self.available_quantity = self.quantity if self.available_quantity is None else int(self.available_quantity)
        self.asset_type = str(self.asset_type or "stock").strip() or "stock"
        if self.market_price in (None, "", 0, 0.0):
            self.market_price = self.avg_price
        else:
            self.market_price = float(self.market_price)
        if self.market_value is None:
            self.market_value = round(self.market_price * self.quantity, 6)
        if self.unrealized_pnl is None:
            self.unrealized_pnl = round((self.market_price - self.avg_price) * self.quantity, 6)
        if self.unrealized_pnl_pct is None:
            if self.avg_price > 0:
                self.unrealized_pnl_pct = round((self.market_price / self.avg_price - 1) * 100, 6)
            else:
                self.unrealized_pnl_pct = None


@dataclass(slots=True)
class BrokerBalance:
    """券商适配层统一资金模型。"""

    cash: float
    available_cash: float
    frozen_cash: float = 0.0
    market_value: float = 0.0
    total_equity: float | None = None
    currency: str = "CNY"
    adapter: str = ""
    updated_at: str = field(default_factory=execution_now_iso)

    def __post_init__(self) -> None:
        self.cash = round(float(self.cash), 6)
        self.available_cash = round(float(self.available_cash), 6)
        self.frozen_cash = round(float(self.frozen_cash), 6)
        self.market_value = round(float(self.market_value), 6)
        self.currency = str(self.currency or "CNY").strip().upper() or "CNY"
        if self.total_equity is None:
            self.total_equity = round(self.cash + self.market_value, 6)
        else:
            self.total_equity = round(float(self.total_equity), 6)


def _normalize_date(value: object) -> str | None:
    if value in (None, ""):
        return None
    return datetime.fromisoformat(str(value)).date().isoformat()


def _optional_price(value: object) -> float | None:
    if value in (None, "", 0, 0.0):
        return None
    return float(value)


__all__ = [
    "BrokerBalance",
    "BrokerPosition",
    "ExecutionSignal",
    "ExecutionSide",
    "OrderResult",
    "OrderStatus",
    "execution_now",
    "execution_now_iso",
]
