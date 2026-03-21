from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from quant_balance.models import MarketBar, Order, Portfolio


class Strategy(ABC):
    name: str = "base-strategy"

    @abstractmethod
    def generate_orders(self, bars: Sequence[MarketBar], portfolio: Portfolio) -> list[Order]:
        """Generate target orders from historical bars and current portfolio."""


class BuyAndHoldStrategy(Strategy):
    name = "buy-and-hold"

    def __init__(self) -> None:
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
