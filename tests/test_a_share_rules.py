from datetime import date, timedelta

import pytest

from quant_balance.backtest import BacktestEngine
from quant_balance.models import AccountConfig, MarketBar, Order, Portfolio
from quant_balance.strategy import Strategy


class ExplicitOrderStrategy(Strategy):
    name = "explicit-order-strategy"

    def __init__(self, order_plan: dict[tuple[str, date], list[Order]]) -> None:
        self.order_plan = order_plan

    def generate_orders(self, bars: list[MarketBar], portfolio: Portfolio) -> list[Order]:
        latest = bars[-1]
        return self.order_plan.get((latest.symbol, latest.date), [])


def test_a_share_buy_and_sell_costs_are_charged() -> None:
    start = date(2026, 1, 1)
    bars = [
        MarketBar(symbol="AAA", date=start, open=10.0, high=10.0, low=10.0, close=10.0, volume=1_000),
        MarketBar(symbol="AAA", date=start + timedelta(days=1), open=10.0, high=10.0, low=10.0, close=10.0, volume=1_000),
    ]
    strategy = ExplicitOrderStrategy(
        {
            ("AAA", start): [Order(symbol="AAA", side="BUY", quantity=100)],
            ("AAA", start + timedelta(days=1)): [Order(symbol="AAA", side="SELL", quantity=100)],
        }
    )
    engine = BacktestEngine(AccountConfig(initial_cash=10_000, max_position_ratio=1.0), strategy)

    result = engine.run(bars)

    total_fees = 100 * 10.0 * (0.0003 + 0.00001) * 2 + 100 * 10.0 * 0.001
    assert len(result.fills) == 2
    assert result.equity_curve[-1] == pytest.approx(10_000 - total_fees)


def test_a_share_t_plus_one_blocks_same_day_sell() -> None:
    day = date(2026, 1, 1)
    bars = [
        MarketBar(symbol="AAA", date=day, open=10.0, high=10.0, low=10.0, close=10.0, volume=1_000),
        MarketBar(symbol="AAA", date=day + timedelta(days=1), open=10.0, high=10.0, low=10.0, close=10.0, volume=1_000),
    ]
    strategy = ExplicitOrderStrategy(
        {
            ("AAA", day): [
                Order(symbol="AAA", side="BUY", quantity=100),
                Order(symbol="AAA", side="SELL", quantity=100),
            ],
            ("AAA", day + timedelta(days=1)): [Order(symbol="AAA", side="SELL", quantity=100)],
        }
    )
    engine = BacktestEngine(AccountConfig(initial_cash=10_000, max_position_ratio=1.0), strategy)

    result = engine.run(bars)

    assert [fill.side for fill in result.fills] == ["BUY", "SELL"]


def test_a_share_limit_up_blocks_buy_fill() -> None:
    start = date(2026, 1, 1)
    bars = [
        MarketBar(symbol="AAA", date=start, open=10.0, high=10.0, low=10.0, close=10.0, volume=1_000),
        MarketBar(symbol="AAA", date=start + timedelta(days=1), open=11.0, high=11.0, low=11.0, close=11.0, volume=1_000),
    ]
    strategy = ExplicitOrderStrategy({("AAA", start + timedelta(days=1)): [Order(symbol="AAA", side="BUY", quantity=100)]})
    engine = BacktestEngine(AccountConfig(initial_cash=10_000, max_position_ratio=1.0), strategy)

    result = engine.run(bars)

    assert result.fills == []


def test_a_share_suspended_bar_skips_order_fill() -> None:
    start = date(2026, 1, 1)
    bars = [
        MarketBar(symbol="AAA", date=start, open=10.0, high=10.0, low=10.0, close=10.0, volume=0),
    ]
    strategy = ExplicitOrderStrategy({("AAA", start): [Order(symbol="AAA", side="BUY", quantity=100)]})
    engine = BacktestEngine(AccountConfig(initial_cash=10_000, max_position_ratio=1.0), strategy)

    result = engine.run(bars)

    assert result.fills == []
    assert result.equity_curve == [10_000.0]
