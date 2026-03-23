"""策略接口 — 定义策略基类与均线交叉策略实现。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from quant_balance.models import MarketBar, Order, Portfolio


class Strategy(ABC):
    name: str = "base-strategy"

    def reset(self) -> None:
        """Reset any strategy state before a new backtest run starts."""

    @abstractmethod
    def generate_orders(self, bars: Sequence[MarketBar], portfolio: Portfolio) -> list[Order]:
        """Generate target orders from historical bars and current portfolio."""


class BuyAndHoldStrategy(Strategy):
    name = "buy-and-hold"

    def __init__(self) -> None:
        self._bought = False

    def reset(self) -> None:
        self._bought = False

    def generate_orders(self, bars: Sequence[MarketBar], portfolio: Portfolio) -> list[Order]:
        if self._bought or not bars:
            return []

        latest = bars[-1]
        if latest.close <= 0:
            return []

        quantity = int(portfolio.cash // latest.close)
        quantity = (quantity // 100) * 100
        if quantity <= 0:
            return []

        self._bought = True
        return [Order(symbol=latest.symbol, side="BUY", quantity=quantity)]


class MovingAverageCrossStrategy(Strategy):
    name = "moving-average-cross"

    def __init__(self, *, short_window: int = 5, long_window: int = 10) -> None:
        if short_window < 2 or long_window < 3 or short_window >= long_window:
            raise ValueError("short_window must be >= 2 and smaller than long_window")
        self.short_window = short_window
        self.long_window = long_window
        self._has_position = False

    def reset(self) -> None:
        self._has_position = False

    def generate_orders(self, bars: Sequence[MarketBar], portfolio: Portfolio) -> list[Order]:
        if len(bars) < self.long_window:
            return []

        latest = bars[-1]
        short_ma = self._average_close(bars[-self.short_window :])
        long_ma = self._average_close(bars[-self.long_window :])
        held_quantity = portfolio.positions.get(latest.symbol).quantity if latest.symbol in portfolio.positions else 0

        if not self._has_position and short_ma > long_ma:
            quantity = int(portfolio.cash // latest.close)
            quantity = (quantity // 100) * 100
            if quantity > 0:
                self._has_position = True
                return [Order(symbol=latest.symbol, side="BUY", quantity=quantity)]

        if held_quantity > 0 and short_ma < long_ma:
            self._has_position = False
            return [Order(symbol=latest.symbol, side="SELL", quantity=held_quantity)]

        self._has_position = held_quantity > 0
        return []

    def _average_close(self, bars: Sequence[MarketBar]) -> float:
        return sum(bar.close for bar in bars) / len(bars)
