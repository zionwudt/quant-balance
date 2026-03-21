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
        for order in orders:
            if not self.market_rules.can_fill_order(order, bar, portfolio, previous_bar):
                continue

            price = self.market_rules.execution_price(order, bar)
            executable_quantity = self._resolve_fill_quantity(order, bar, portfolio, price)
            if executable_quantity <= 0:
                continue

            fill_order = Order(symbol=order.symbol, side=order.side, quantity=executable_quantity)
            fees = self.market_rules.estimate_fees(fill_order, price)
            if not self.risk_manager.validate_order(fill_order, price, portfolio, fees.total):
                continue

            if fill_order.side == "BUY":
                cost = fill_order.quantity * price
                portfolio.cash -= cost + fees.total
                position = portfolio.positions.get(fill_order.symbol)
                if position is None:
                    position = Position(symbol=fill_order.symbol)
                    portfolio.positions[fill_order.symbol] = position
                total_cost = position.avg_price * position.quantity + cost
                position.quantity += fill_order.quantity
                position.avg_price = total_cost / position.quantity
                self.market_rules.apply_fill(fill_order, bar, position)

            elif fill_order.side == "SELL":
                position = portfolio.positions[fill_order.symbol]
                portfolio.cash += fill_order.quantity * price - fees.total
                position.quantity -= fill_order.quantity
                if position.quantity == 0:
                    position.avg_price = 0.0
                    position.last_buy_date = None

            result.fills.append(
                Fill(symbol=fill_order.symbol, side=fill_order.side, quantity=fill_order.quantity, price=price, date=bar.date)
            )

    def _resolve_fill_quantity(self, order: Order, bar: MarketBar, portfolio: Portfolio, price: float) -> int:
        quantity = self.market_rules.volume_capped_quantity(order.quantity, bar)
        quantity = self._round_down_to_lot(quantity)
        if quantity <= 0:
            return 0

        if order.side == "BUY":
            quantity = min(quantity, self._max_buy_quantity(order, portfolio, price))
        else:
            position = portfolio.positions.get(order.symbol)
            if position is None:
                return 0
            quantity = min(quantity, position.quantity)

        return self._round_down_to_lot(quantity)

    def _max_buy_quantity(self, order: Order, portfolio: Portfolio, price: float) -> int:
        held_symbols = {symbol for symbol, pos in portfolio.positions.items() if pos.quantity > 0}
        if order.symbol not in held_symbols and len(held_symbols) >= self.config.max_positions:
            return 0

        fee_rate = self.config.commission_rate + self.config.transfer_fee_rate
        per_share_cost = price * (1 + fee_rate)
        if per_share_cost <= 0:
            return 0

        max_by_cash = int(portfolio.cash / per_share_cost)
        equity = portfolio.total_equity()
        if equity <= 0:
            return 0
        max_by_position_ratio = int((equity * self.config.max_position_ratio) / per_share_cost)
        return min(max_by_cash, max_by_position_ratio)

    def _round_down_to_lot(self, quantity: int) -> int:
        if quantity <= 0:
            return 0
        return (quantity // self.config.lot_size) * self.config.lot_size
