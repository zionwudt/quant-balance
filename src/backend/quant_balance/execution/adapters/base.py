"""券商适配层抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from quant_balance.execution.models import BrokerBalance, BrokerPosition, ExecutionSignal, OrderResult


class BrokerAdapter(ABC):
    """统一的券商 / 手工执行适配器接口。"""

    adapter_name: str

    def __init__(self, *, adapter_name: str) -> None:
        self.adapter_name = str(adapter_name).strip().lower()

    def normalize_signal(self, signal: ExecutionSignal | Mapping[str, object]) -> ExecutionSignal:
        """把外部信号字典或模型统一转成 ExecutionSignal。"""

        if isinstance(signal, ExecutionSignal):
            return signal
        if isinstance(signal, Mapping):
            return ExecutionSignal.from_signal_payload(signal)
        raise TypeError(f"不支持的 signal 类型 {type(signal)!r}")

    @abstractmethod
    def place_order(self, signal: ExecutionSignal | Mapping[str, object]) -> OrderResult:
        """提交一笔执行委托。"""

    @abstractmethod
    def query_positions(self) -> list[BrokerPosition]:
        """查询当前持仓。"""

    @abstractmethod
    def query_balance(self) -> BrokerBalance:
        """查询当前资金余额。"""

    def adapter_info(self) -> dict[str, Any]:
        """返回适配器元信息。"""

        return {"adapter": self.adapter_name}


__all__ = ["BrokerAdapter"]
