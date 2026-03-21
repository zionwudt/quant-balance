from __future__ import annotations

from dataclasses import dataclass

from quant_balance.models import AccountConfig, MarketBar, Order, Portfolio, Position


@dataclass(slots=True)
class AShareFees:
    commission: float
    transfer_fee: float
    stamp_duty: float

    @property
    def total(self) -> float:
        return self.commission + self.transfer_fee + self.stamp_duty


class AShareMarketRules:
    def __init__(self, config: AccountConfig) -> None:
        self.config = config

    def can_fill_order(
        self,
        order: Order,
        bar: MarketBar,
        portfolio: Portfolio,
        previous_bar: MarketBar | None,
    ) -> bool:
        if bar.volume <= 0:
            return False

        if previous_bar is not None:
            if order.side == "BUY" and self._is_limit_up(bar, previous_bar.close):
                return False
            if order.side == "SELL" and self._is_limit_down(bar, previous_bar.close):
                return False

        if order.side == "SELL":
            position = portfolio.positions.get(order.symbol)
            if position is None or position.last_buy_date is None:
                return False
            if position.last_buy_date >= bar.date:
                return False

        return True

    def estimate_fees(self, order: Order, price: float) -> AShareFees:
        turnover = order.quantity * price
        commission = turnover * self.config.commission_rate
        transfer_fee = turnover * self.config.transfer_fee_rate
        stamp_duty = turnover * self.config.stamp_duty_rate if order.side == "SELL" else 0.0
        return AShareFees(commission=commission, transfer_fee=transfer_fee, stamp_duty=stamp_duty)

    def apply_fill(self, order: Order, bar: MarketBar, position: Position) -> None:
        if order.side == "BUY":
            position.last_buy_date = bar.date

    @staticmethod
    def _is_limit_up(bar: MarketBar, previous_close: float) -> bool:
        limit_price = round(previous_close * 1.10, 2)
        return bar.close >= limit_price and bar.high >= limit_price

    @staticmethod
    def _is_limit_down(bar: MarketBar, previous_close: float) -> bool:
        limit_price = round(previous_close * 0.90, 2)
        return bar.close <= limit_price and bar.low <= limit_price
