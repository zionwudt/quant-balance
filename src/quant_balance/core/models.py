"""数据模型 — 行情、订单、持仓、账户配置等核心数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

# 订单方向只保留最小集合，方便在策略、风控、撮合之间传递。
Side = Literal["BUY", "SELL"]
# 滑点目前只支持“关闭”或“按比例偏移”两种简化模式。
SlippageMode = Literal["none", "pct"]
# 价格视角可选纯原始价格，或“策略前复权 + 交易原始价”的双轨模式。
PriceAdjustmentMode = Literal["none", "forward"]


@dataclass(slots=True)
class MarketBar:
    """单个交易日的标准 OHLCV 行情。

    回测引擎、策略和页面 CSV 导入都会先统一转成这个结构，避免后续模块各自解析。
    """

    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(slots=True)
class Position:
    """组合中的单个持仓快照。"""

    symbol: str
    quantity: int = 0
    avg_price: float = 0.0
    last_buy_date: date | None = None

    @property
    def market_value(self) -> float:
        """返回按持仓均价估出的市值，作为缺少最新价时的兜底估值。"""

        return self.quantity * self.avg_price


@dataclass(slots=True)
class Order:
    """策略输出的目标委托。

    这里只描述“想买/卖多少”，并不代表一定能成交；是否可成交由市场规则和风控决定。
    """

    symbol: str
    side: Side
    quantity: int


@dataclass(slots=True)
class Fill:
    """已成交回报。

    回测报告、成交统计和 closed trade 计算都基于这个结构。
    """

    symbol: str
    side: Side
    quantity: int
    price: float
    date: date


@dataclass(slots=True)
class AccountConfig:
    """账户和回测参数配置。

    这里把资金、仓位限制、费用、滑点和市场视角放在一个对象里，
    让回测引擎初始化后不再依赖零散参数。
    """

    initial_cash: float = 100_000.0
    max_position_ratio: float = 0.2
    max_positions: int = 5
    stop_loss_ratio: float = 0.08
    max_drawdown_ratio: float = 0.1
    lot_size: int = 100
    market: str = "A_SHARE"
    commission_rate: float = 0.0003
    transfer_fee_rate: float = 0.00001
    stamp_duty_rate: float = 0.001
    slippage_mode: SlippageMode = "none"
    slippage_rate: float = 0.0
    max_volume_participation: float = 1.0
    price_adjustment_mode: PriceAdjustmentMode = "forward"


@dataclass(slots=True)
class Portfolio:
    """组合状态。

    `cash` 和 `positions` 是回测循环中的可变状态，`peak_equity` 则用于最大回撤监控。
    """

    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    peak_equity: float = 0.0

    def total_equity(self, latest_prices: dict[str, float] | None = None) -> float:
        """计算组合总权益，即现金加上按市价估值后的持仓市值。

        当某个标的暂时没有最新价时，退化为使用持仓均价估值，保证函数始终可用。
        """

        latest_prices = latest_prices or {}
        market_value = 0.0
        for symbol, position in self.positions.items():
            price = latest_prices.get(symbol, position.avg_price)
            market_value += position.quantity * price
        return self.cash + market_value
