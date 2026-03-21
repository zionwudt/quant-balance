from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from quant_balance.models import AccountConfig, Fill, MarketBar, Order, Portfolio, Position
from quant_balance.risk import RiskManager
from quant_balance.strategy import Strategy


@dataclass(slots=True)
class BacktestResult:
    equity_curve: list[float] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    halted: bool = False


class BacktestEngine:
    def __init__(self, config: AccountConfig, strategy: Strategy) -> None:
        self.config = config
        self.strategy = strategy
        self.risk_manager = RiskManager(config)

    def run(self, bars: Sequence[MarketBar]) -> BacktestResult:
        self.strategy.reset()
        portfolio = Portfolio(cash=self.config.initial_cash, peak_equity=self.config.initial_cash)
        result = BacktestResult()

        history: list[MarketBar] = []
        latest_prices: dict[str, float] = {}
        for bar in bars:
            history.append(bar)
            latest_prices[bar.symbol] = bar.close
            orders = self.strategy.generate_orders(history, portfolio)
            self._apply_orders(orders, bar.close, portfolio, result)

            equity = portfolio.total_equity(latest_prices)
            portfolio.peak_equity = max(portfolio.peak_equity, equity)
            result.equity_curve.append(equity)

            if self.risk_manager.drawdown_exceeded(equity, portfolio.peak_equity):
                result.halted = True
                break

        return result

    def _apply_orders(
        self,
        orders: Sequence[Order],
        price: float,
        portfolio: Portfolio,
        result: BacktestResult,
    ) -> None:
        for order in orders:
            if not self.risk_manager.validate_order(order, price, portfolio):
                continue

            if order.side == "BUY":
                cost = order.quantity * price
                portfolio.cash -= cost
                position = portfolio.positions.get(order.symbol)
                if position is None:
                    position = Position(symbol=order.symbol)
                    portfolio.positions[order.symbol] = position
                total_cost = position.avg_price * position.quantity + cost
                position.quantity += order.quantity
                position.avg_price = total_cost / position.quantity

            elif order.side == "SELL":
                position = portfolio.positions[order.symbol]
                portfolio.cash += order.quantity * price
                position.quantity -= order.quantity
                if position.quantity == 0:
                    position.avg_price = 0.0

            result.fills.append(Fill(symbol=order.symbol, side=order.side, quantity=order.quantity, price=price))
