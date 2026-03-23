"""A 股市场规则 — 涨跌停判定、T+1 限制与手续费计算。"""

from __future__ import annotations

from dataclasses import dataclass

from .models import AccountConfig, MarketBar, Order, Portfolio, Position


@dataclass(slots=True)
class AShareFees:
    """A 股单笔成交费用拆分。"""

    commission: float
    transfer_fee: float
    stamp_duty: float

    @property
    def total(self) -> float:
        """返回单笔交易的总费用。"""

        return self.commission + self.transfer_fee + self.stamp_duty


class AShareMarketRules:
    """A 股市场撮合规则的简化实现。

    目前覆盖涨跌停、T+1、滑点、成交量参与比例和费用估算。
    """

    def __init__(self, config: AccountConfig) -> None:
        self.config = config

    def can_fill_order(
        self,
        order: Order,
        bar: MarketBar,
        portfolio: Portfolio,
        previous_bar: MarketBar | None,
    ) -> bool:
        """判断订单在当前交易日是否允许成交。"""

        # 没有成交量的 bar 在这里视为无法成交，避免“停牌仍成交”的假象。
        if bar.volume <= 0:
            return False

        if previous_bar is not None:
            # 用前收盘价推导当日理论涨跌停价，限制追涨停买入和跌停卖出。
            if order.side == "BUY" and self._is_limit_up(bar, previous_bar.close):
                return False
            if order.side == "SELL" and self._is_limit_down(bar, previous_bar.close):
                return False

        if order.side == "SELL":
            # T+1：当天买入的仓位不能在同一个交易日卖出。
            position = portfolio.positions.get(order.symbol)
            if position is None or position.last_buy_date is None:
                return False
            if position.last_buy_date >= bar.date:
                return False

        return True

    def execution_price(self, order: Order, bar: MarketBar) -> float:
        """返回应用滑点模型后的成交价格。"""

        price = bar.close
        if self.config.slippage_mode == "pct":
            if order.side == "BUY":
                price *= 1 + self.config.slippage_rate
            else:
                price *= 1 - self.config.slippage_rate
        return price

    def volume_capped_quantity(self, quantity: int, bar: MarketBar) -> int:
        """按配置的成交量参与比例限制可成交数量。"""

        participation = min(max(self.config.max_volume_participation, 0.0), 1.0)
        if participation <= 0:
            return 0

        volume_limit = int(bar.volume * participation)
        return min(quantity, volume_limit)

    def estimate_fees(self, order: Order, price: float) -> AShareFees:
        """估算单笔订单的佣金、过户费和印花税。"""

        turnover = order.quantity * price
        commission = turnover * self.config.commission_rate
        transfer_fee = turnover * self.config.transfer_fee_rate
        stamp_duty = turnover * self.config.stamp_duty_rate if order.side == "SELL" else 0.0
        return AShareFees(commission=commission, transfer_fee=transfer_fee, stamp_duty=stamp_duty)

    def apply_fill(self, order: Order, bar: MarketBar, position: Position) -> None:
        """把成交后的市场规则副作用写回持仓。"""

        if order.side == "BUY":
            position.last_buy_date = bar.date

    @staticmethod
    def _is_limit_up(bar: MarketBar, previous_close: float) -> bool:
        """判断当前交易日是否基本处于 10% 涨停封板状态。"""

        limit_price = round(previous_close * 1.10, 2)
        return bar.close >= limit_price and bar.high >= limit_price

    @staticmethod
    def _is_limit_down(bar: MarketBar, previous_close: float) -> bool:
        """判断当前交易日是否基本处于 10% 跌停封板状态。"""

        limit_price = round(previous_close * 0.90, 2)
        return bar.close <= limit_price and bar.low <= limit_price
