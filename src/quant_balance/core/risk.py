"""风控管理 — 持仓比例、回撤与仓位数量控制。"""

from __future__ import annotations

from .models import AccountConfig, Order, Portfolio


class RiskManager:
    """账户级风控检查。

    这里负责“这笔单能不能下”和“账户是否应当因回撤停止回测”两类判断。
    """

    def __init__(self, config: AccountConfig) -> None:
        self.config = config

    def validate_order(
        self,
        order: Order,
        price: float,
        portfolio: Portfolio,
        estimated_fee: float = 0.0,
    ) -> bool:
        """校验订单数量、现金、仓位限制和可卖数量。"""

        if order.quantity <= 0 or price <= 0:
            return False

        # A 股默认按整手交易，非整手数量在进入撮合前直接视为非法。
        if order.quantity % self.config.lot_size != 0:
            return False

        if order.side == "BUY":
            cost = order.quantity * price + estimated_fee
            # 买入时先检查现金，再检查持仓比例和持仓数限制。
            if cost > portfolio.cash:
                return False

            equity = portfolio.total_equity()
            if equity <= 0:
                return False

            if cost / equity > self.config.max_position_ratio:
                return False

            held_symbols = {symbol for symbol, pos in portfolio.positions.items() if pos.quantity > 0}
            if order.symbol not in held_symbols and len(held_symbols) >= self.config.max_positions:
                return False

        if order.side == "SELL":
            # 卖出只允许基于当前真实持仓，避免出现裸卖空。
            position = portfolio.positions.get(order.symbol)
            if position is None or order.quantity > position.quantity:
                return False

        return True

    def drawdown_exceeded(self, equity: float, peak_equity: float) -> bool:
        """判断当前回撤是否触及配置的停止阈值。"""

        if peak_equity <= 0:
            return False
        drawdown = (peak_equity - equity) / peak_equity
        return drawdown >= self.config.max_drawdown_ratio
