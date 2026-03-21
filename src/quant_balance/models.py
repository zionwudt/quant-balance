from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

Side = Literal["BUY", "SELL"]


@dataclass(slots=True)
class MarketBar:
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(slots=True)
class Position:
    symbol: str
    quantity: int = 0
    avg_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.avg_price


@dataclass(slots=True)
class Order:
    symbol: str
    side: Side
    quantity: int


@dataclass(slots=True)
class Fill:
    symbol: str
    side: Side
    quantity: int
    price: float


@dataclass(slots=True)
class AccountConfig:
    initial_cash: float = 100_000.0
    max_position_ratio: float = 0.2
    max_positions: int = 5
    stop_loss_ratio: float = 0.08
    max_drawdown_ratio: float = 0.1
    lot_size: int = 100
    market: str = "A_SHARE"


@dataclass(slots=True)
class Portfolio:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    peak_equity: float = 0.0

    def total_equity(self, latest_prices: dict[str, float] | None = None) -> float:
        latest_prices = latest_prices or {}
        market_value = 0.0
        for symbol, position in self.positions.items():
            price = latest_prices.get(symbol, position.avg_price)
            market_value += position.quantity * price
        return self.cash + market_value
