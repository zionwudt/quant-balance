from __future__ import annotations

from quant_balance.models import AccountConfig, Order, Portfolio


class RiskManager:
    def __init__(self, config: AccountConfig) -> None:
        self.config = config

    def validate_order(self, order: Order, price: float, portfolio: Portfolio) -> bool:
        if order.quantity <= 0 or price <= 0:
            return False

        if order.quantity % self.config.lot_size != 0:
            return False

        if order.side == "BUY":
            cost = order.quantity * price
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
            position = portfolio.positions.get(order.symbol)
            if position is None or order.quantity > position.quantity:
                return False

        return True

    def drawdown_exceeded(self, equity: float, peak_equity: float) -> bool:
        if peak_equity <= 0:
            return False
        drawdown = (peak_equity - equity) / peak_equity
        return drawdown >= self.config.max_drawdown_ratio
