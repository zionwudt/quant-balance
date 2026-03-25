"""执行适配器注册与快捷导出。"""

from quant_balance.execution.adapters.base import BrokerAdapter
from quant_balance.execution.adapters.manual import ManualAdapter
from quant_balance.execution.adapters.qmt import QmtAdapter

ADAPTER_REGISTRY = {
    "manual": ManualAdapter,
    "qmt": QmtAdapter,
}


def build_broker_adapter(name: str = "manual", **kwargs) -> BrokerAdapter:
    """按名称构建执行适配器。"""

    normalized = str(name or "").strip().lower()
    adapter_cls = ADAPTER_REGISTRY.get(normalized)
    if adapter_cls is None:
        supported = ", ".join(sorted(ADAPTER_REGISTRY))
        raise ValueError(f"未知执行适配器 {name!r}，当前支持: {supported}")
    return adapter_cls(**kwargs)


__all__ = [
    "ADAPTER_REGISTRY",
    "BrokerAdapter",
    "ManualAdapter",
    "QmtAdapter",
    "build_broker_adapter",
]
