from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from quant_balance.market_rules import AShareMarketRules
from quant_balance.models import AccountConfig, Fill, MarketBar, Order, Portfolio, Position
from quant_balance.report import BacktestReport, generate_report
from quant_balance.risk import RiskManager
from quant_balance.strategy import Strategy


@dataclass(slots=True)
class BacktestResult:
    equity_curve: list[float] = field(default_factory=list)
    equity_dates: list[date] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    halted: bool = False
    report: BacktestReport | None = None


class BacktestEngine:
    def __init__(self, config: AccountConfig, strategy: Strategy) -> None:
        self.config = config
        self.strategy = strategy
        self.risk_manager = RiskManager(config)
        self.market_rules = AShareMarketRules(config)

    def run(self, bars: Sequence[MarketBar]) -> BacktestResult:
        self.strategy.reset()
        portfolio = Portfolio(cash=self.config.initial_cash, peak_equity=self.config.initial_cash)
        result = BacktestResult()

        history: list[MarketBar] = []
        latest_prices: dict[str, float] = {}
        latest_bars: dict[str, MarketBar] = {}
        for bar in bars:
            history.append(bar)
            previous_bar = latest_bars.get(bar.symbol)
            latest_prices[bar.symbol] = bar.close
            latest_bars[bar.symbol] = bar
            orders = self.strategy.generate_orders(history, portfolio)
            self._apply_orders(orders, bar, previous_bar, portfolio, result)

            equity = portfolio.total_equity(latest_prices)
            portfolio.peak_equity = max(portfolio.peak_equity, equity)
            result.equity_curve.append(equity)
            result.equity_dates.append(bar.date)

            if self.risk_manager.drawdown_exceeded(equity, portfolio.peak_equity):
                result.halted = True
                break

        result.report = generate_report(
            initial_equity=self.config.initial_cash,
            equity_curve=result.equity_curve,
            equity_dates=result.equity_dates,
            fills=result.fills,
        )
        return result

    def _apply_orders(
        self,
        orders: Sequence[Order],
        bar: MarketBar,
        previous_bar: MarketBar | None,
        portfolio: Portfolio,
        result: BacktestResult,
    ) -> None:
        price = bar.close
        for order in orders:
            fees = self.market_rules.estimate_fees(order, price)
            if not self.risk_manager.validate_order(order, price, portfolio, fees.total):
                continue
            if not self.market_rules.can_fill_order(order, bar, portfolio, previous_bar):
                continue

            if order.side == "BUY":
                cost = order.quantity * price
                portfolio.cash -= cost + fees.total
                position = portfolio.positions.get(order.symbol)
                if position is None:
                    position = Position(symbol=order.symbol)
                    portfolio.positions[order.symbol] = position
                total_cost = position.avg_price * position.quantity + cost
                position.quantity += order.quantity
                position.avg_price = total_cost / position.quantity
                self.market_rules.apply_fill(order, bar, position)

            elif order.side == "SELL":
                position = portfolio.positions[order.symbol]
                portfolio.cash += order.quantity * price - fees.total
                position.quantity -= order.quantity
                if position.quantity == 0:
                    position.avg_price = 0.0
                    position.last_buy_date = None

            result.fills.append(Fill(symbol=order.symbol, side=order.side, quantity=order.quantity, price=price, date=bar.date))
