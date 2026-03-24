"""回测引擎 — 按日线驱动策略信号、撮合成交与风控检查。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from .corporate_actions import CorporateAction, CorporateActionBook
from .market_rules import AShareMarketRules
from .models import AccountConfig, Fill, MarketBar, Order, Portfolio, Position
from .report import BacktestReport, generate_report
from .risk import RiskManager
from .strategy import Strategy


@dataclass(slots=True)
class BacktestResult:
    """一次回测运行的完整产物。"""

    equity_curve: list[float] = field(default_factory=list)
    equity_dates: list[date] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    halted: bool = False
    report: BacktestReport | None = None


class BacktestEngine:
    """日线回测引擎。

    它负责把“行情序列 + 策略”转成“成交、权益曲线和统计报表”。
    """

    def __init__(self, config: AccountConfig, strategy: Strategy) -> None:
        self.config = config
        self.strategy = strategy
        self.risk_manager = RiskManager(config)
        self.market_rules = AShareMarketRules(config)

    def run(
        self,
        bars: Sequence[MarketBar],
        corporate_actions: Sequence[CorporateAction] | None = None,
        indicator_bars: Sequence[MarketBar] | None = None,
    ) -> BacktestResult:
        """对给定行情序列执行一次完整回测。"""

        # 每次运行前都重置策略和账户状态，保证多次回测彼此隔离。
        self.strategy.reset()
        portfolio = Portfolio(cash=self.config.initial_cash, peak_equity=self.config.initial_cash)
        result = BacktestResult()
        action_book = CorporateActionBook(corporate_actions)

        trade_bars = list(bars)
        signal_bars = self._resolve_signal_bars(
            trade_bars=trade_bars,
            indicator_bars=indicator_bars,
            action_book=action_book,
        )

        history: list[MarketBar] = []
        latest_prices: dict[str, float] = {}
        latest_bars: dict[str, MarketBar] = {}
        for trade_bar, signal_bar in zip(trade_bars, signal_bars):
            # 除权除息先作用到持仓，再让策略看到当天 K 线，顺序上更接近真实账户状态。
            action_book.apply_to_portfolio(symbol=trade_bar.symbol, ex_date=trade_bar.date, portfolio=portfolio)
            history.append(signal_bar)
            previous_bar = latest_bars.get(trade_bar.symbol)
            latest_prices[trade_bar.symbol] = trade_bar.close
            latest_bars[trade_bar.symbol] = trade_bar

            # 策略拿到的是截至当前 K 线的历史数据和最新组合状态。
            orders = self.strategy.generate_orders(history, portfolio)
            self._apply_orders(orders, trade_bar, previous_bar, portfolio, result)

            # 成交完成后再记权益，确保曲线反映的是“当日收盘后”的账户状态。
            equity = portfolio.total_equity(latest_prices)
            portfolio.peak_equity = max(portfolio.peak_equity, equity)
            result.equity_curve.append(equity)
            result.equity_dates.append(trade_bar.date)

            # 一旦回撤超过阈值，就中止后续交易日处理。
            if self.risk_manager.drawdown_exceeded(equity, portfolio.peak_equity):
                result.halted = True
                break

        # 即使中途提前停止，也用已经产生的曲线和成交生成报告。
        result.report = generate_report(
            initial_equity=self.config.initial_cash,
            equity_curve=result.equity_curve,
            equity_dates=result.equity_dates,
            fills=result.fills,
        )
        return result

    def _resolve_signal_bars(
        self,
        *,
        trade_bars: Sequence[MarketBar],
        indicator_bars: Sequence[MarketBar] | None,
        action_book: CorporateActionBook,
    ) -> list[MarketBar]:
        """决定策略应该看到哪套价格序列。"""

        trade_bar_list = list(trade_bars)
        if self.config.price_adjustment_mode == "none":
            return trade_bar_list

        if indicator_bars is not None:
            resolved = list(indicator_bars)
            self._validate_bar_alignment(trade_bar_list, resolved)
            return resolved

        if action_book.has_actions and trade_bar_list:
            return action_book.apply_forward_adjustments(trade_bar_list)

        return trade_bar_list

    def _validate_bar_alignment(
        self,
        trade_bars: Sequence[MarketBar],
        indicator_bars: Sequence[MarketBar],
    ) -> None:
        """确保两套 bar 的时序完全对齐，避免把错误价格错配到别的交易日。"""

        if len(trade_bars) != len(indicator_bars):
            raise ValueError("indicator_bars 与 bars 的长度不一致，无法进行双轨回测。")

        for trade_bar, indicator_bar in zip(trade_bars, indicator_bars):
            if trade_bar.symbol != indicator_bar.symbol or trade_bar.date != indicator_bar.date:
                raise ValueError("indicator_bars 与 bars 的 symbol/date 不一致，无法进行双轨回测。")

    def _apply_orders(
        self,
        orders: Sequence[Order],
        bar: MarketBar,
        previous_bar: MarketBar | None,
        portfolio: Portfolio,
        result: BacktestResult,
    ) -> None:
        """把策略订单尝试撮合到当前交易日，并原地更新账户状态。"""

        for order in orders:
            # 第一道门：市场规则。这里过滤涨跌停、T+1、无量等无法成交的订单。
            if not self.market_rules.can_fill_order(order, bar, portfolio, previous_bar):
                continue

            price = self.market_rules.execution_price(order, bar)
            executable_quantity = self._resolve_fill_quantity(order, bar, portfolio, price)
            if executable_quantity <= 0:
                continue

            fill_order = Order(symbol=order.symbol, side=order.side, quantity=executable_quantity)
            fees = self.market_rules.estimate_fees(fill_order, price)
            # 第二道门：账户风控。这里检查现金、仓位比例、持仓数和卖出持仓是否足够。
            if not self.risk_manager.validate_order(fill_order, price, portfolio, fees.total):
                continue

            if fill_order.side == "BUY":
                cost = fill_order.quantity * price
                portfolio.cash -= cost + fees.total
                position = portfolio.positions.get(fill_order.symbol)
                if position is None:
                    # 首次买入该标的时动态创建持仓对象。
                    position = Position(symbol=fill_order.symbol)
                    portfolio.positions[fill_order.symbol] = position

                # 持仓成本按加权平均价更新，便于后续估值和展示。
                total_cost = position.avg_price * position.quantity + cost
                position.quantity += fill_order.quantity
                position.avg_price = total_cost / position.quantity
                self.market_rules.apply_fill(fill_order, bar, position)

            elif fill_order.side == "SELL":
                position = portfolio.positions[fill_order.symbol]
                portfolio.cash += fill_order.quantity * price - fees.total
                position.quantity -= fill_order.quantity
                if position.quantity == 0:
                    # 清仓后把均价和最近买入日清空，避免残留状态污染下一次交易。
                    position.avg_price = 0.0
                    position.last_buy_date = None

            # 成交回报是报表层唯一信任的“交易事实来源”。
            result.fills.append(
                Fill(symbol=fill_order.symbol, side=fill_order.side, quantity=fill_order.quantity, price=price, date=bar.date)
            )

    def _resolve_fill_quantity(self, order: Order, bar: MarketBar, portfolio: Portfolio, price: float) -> int:
        """在成交量、整手和持仓约束下计算可成交数量。"""

        # 先按照成交量参与比例裁剪，再按整手取整。
        quantity = self.market_rules.volume_capped_quantity(order.quantity, bar)
        quantity = self._round_down_to_lot(quantity)
        if quantity <= 0:
            return 0

        if order.side == "BUY":
            # 买入再额外受现金和仓位限制约束。
            quantity = min(quantity, self._max_buy_quantity(order, portfolio, price))
        else:
            position = portfolio.positions.get(order.symbol)
            if position is None:
                return 0
            # 卖出最多只能卖到账户里真实存在的数量。
            quantity = min(quantity, position.quantity)

        return self._round_down_to_lot(quantity)

    def _max_buy_quantity(self, order: Order, portfolio: Portfolio, price: float) -> int:
        """结合现金和仓位规则计算买入数量上限。"""

        held_symbols = {symbol for symbol, pos in portfolio.positions.items() if pos.quantity > 0}
        if order.symbol not in held_symbols and len(held_symbols) >= self.config.max_positions:
            return 0

        # 这里用买入侧确定可支配股数时，把佣金和过户费也算进去，避免现金略微超支。
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
        """按市场最小交易单位向下取整。"""

        if quantity <= 0:
            return 0
        return (quantity // self.config.lot_size) * self.config.lot_size
