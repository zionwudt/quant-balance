"""轻量配置模型。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class BacktestConfig:
    """单股回测配置。"""

    strategy: str = "sma_cross"
    cash: float = 100_000.0
    commission: float = 0.001
    params: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class OptimizeConfig:
    """参数优化配置。"""

    strategy: str = "sma_cross"
    cash: float = 100_000.0
    commission: float = 0.001
    maximize: str = "Sharpe Ratio"
    param_ranges: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ScreeningConfig:
    """批量筛选配置。"""

    signal: str = "sma_cross"
    signal_params: dict[str, object] = field(default_factory=dict)
    top_n: int = 20
    cash: float = 100_000.0


__all__ = [
    "BacktestConfig",
    "OptimizeConfig",
    "ScreeningConfig",
]
