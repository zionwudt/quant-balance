"""策略接口 — 定义策略基类与均线交叉策略实现。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from .models import MarketBar, Order, Portfolio


class Strategy(ABC):
    """策略抽象基类。

    回测引擎只依赖这个最小接口，因此替换策略时不需要改撮合和报表层。
    """

    name: str = "base-strategy"

    def reset(self) -> None:
        """在每次回测前重置策略状态。

        同一个策略实例可能被复用于多次回测，因此任何带状态的策略都要在这里清零。
        """

    @abstractmethod
    def generate_orders(self, bars: Sequence[MarketBar], portfolio: Portfolio) -> list[Order]:
        """根据历史行情和当前组合状态生成目标订单。"""


class BuyAndHoldStrategy(Strategy):
    """最小示例策略：首次有足够现金时一次性买入并长期持有。"""

    name = "buy-and-hold"

    def __init__(self) -> None:
        self._bought = False

    def reset(self) -> None:
        """允许同一个策略实例在多次独立回测之间复用。"""

        self._bought = False

    def generate_orders(self, bars: Sequence[MarketBar], portfolio: Portfolio) -> list[Order]:
        """在最新交易日尝试买入一次，之后不再继续下单。"""

        if self._bought or not bars:
            return []

        latest = bars[-1]
        if latest.close <= 0:
            return []

        # 该示例故意按“现金尽量买满”实现，目的是给回测链路提供最简单稳定的信号源。
        quantity = int(portfolio.cash // latest.close)
        quantity = (quantity // 100) * 100
        if quantity <= 0:
            return []

        self._bought = True
        return [Order(symbol=latest.symbol, side="BUY", quantity=quantity)]


class MovingAverageCrossStrategy(Strategy):
    """简单均线交叉策略。

    短均线上穿长均线时开仓，下穿时平仓；这里只维护单标的、全仓式示例逻辑。
    """

    name = "moving-average-cross"

    def __init__(self, *, short_window: int = 5, long_window: int = 10) -> None:
        if short_window < 2 or long_window < 3 or short_window >= long_window:
            raise ValueError("short_window must be >= 2 and smaller than long_window")
        self.short_window = short_window
        self.long_window = long_window
        self._has_position = False

    def reset(self) -> None:
        """清空上一轮回测留下的持仓状态。"""

        self._has_position = False

    def generate_orders(self, bars: Sequence[MarketBar], portfolio: Portfolio) -> list[Order]:
        """根据最新均线关系生成买卖订单。"""

        if len(bars) < self.long_window:
            return []

        latest = bars[-1]
        short_ma = self._average_close(bars[-self.short_window :])
        long_ma = self._average_close(bars[-self.long_window :])
        held_quantity = portfolio.positions.get(latest.symbol).quantity if latest.symbol in portfolio.positions else 0

        # 金叉且当前空仓时，尝试按剩余现金整手买入。
        if not self._has_position and short_ma > long_ma:
            quantity = int(portfolio.cash // latest.close)
            quantity = (quantity // 100) * 100
            if quantity > 0:
                self._has_position = True
                return [Order(symbol=latest.symbol, side="BUY", quantity=quantity)]

        # 死叉且已有持仓时，一次性全部卖出。
        if held_quantity > 0 and short_ma < long_ma:
            self._has_position = False
            return [Order(symbol=latest.symbol, side="SELL", quantity=held_quantity)]

        # 把真实持仓同步回内部状态，避免因为撮合失败导致策略状态与账户状态脱节。
        self._has_position = held_quantity > 0
        return []

    def _average_close(self, bars: Sequence[MarketBar]) -> float:
        """计算一个窗口内收盘价的算术平均值。"""

        return sum(bar.close for bar in bars) / len(bars)
