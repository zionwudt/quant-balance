from datetime import date, timedelta

import pytest

from quant_balance.core.backtest import BacktestEngine
from quant_balance.core.corporate_actions import CorporateAction, CorporateActionBook
from quant_balance.core.models import AccountConfig, MarketBar, Order, Portfolio
from quant_balance.core.strategy import Strategy


class ExplicitOrderStrategy(Strategy):
    name = "explicit-order-strategy"

    def __init__(self, order_plan: dict[tuple[str, date], list[Order]]) -> None:
        self.order_plan = order_plan

    def generate_orders(self, bars: list[MarketBar], portfolio: Portfolio) -> list[Order]:
        latest = bars[-1]
        return self.order_plan.get((latest.symbol, latest.date), [])


class AdjustedPriceTriggerStrategy(Strategy):
    name = "adjusted-price-trigger"

    def __init__(self, trigger_price: float, trigger_bar_count: int | None = None) -> None:
        self.trigger_price = trigger_price
        self.trigger_bar_count = trigger_bar_count
        self._submitted = False

    def generate_orders(self, bars: list[MarketBar], portfolio: Portfolio) -> list[Order]:
        if self._submitted or not bars:
            return []

        latest = bars[-1]
        if self.trigger_bar_count is not None and len(bars) != self.trigger_bar_count:
            return []
        if latest.close != self.trigger_price:
            return []

        self._submitted = True
        return [Order(symbol=latest.symbol, side="BUY", quantity=100)]


def test_corporate_action_applies_cash_dividend_and_bonus_shares_to_existing_position() -> None:
    start = date(2026, 1, 5)
    bars = [
        MarketBar(symbol="AAA", date=start, open=10.0, high=10.0, low=10.0, close=10.0, volume=10_000),
        MarketBar(symbol="AAA", date=start + timedelta(days=1), open=9.5, high=9.5, low=9.5, close=9.5, volume=10_000),
        MarketBar(symbol="AAA", date=start + timedelta(days=2), open=9.5, high=9.5, low=9.5, close=9.5, volume=10_000),
    ]
    corporate_actions = [
        CorporateAction(
            symbol="AAA",
            ex_date=start + timedelta(days=1),
            cash_dividend_per_share=0.5,
            share_ratio=0.2,
        )
    ]
    strategy = ExplicitOrderStrategy({("AAA", start): [Order(symbol="AAA", side="BUY", quantity=100)]})
    engine = BacktestEngine(
        AccountConfig(
            initial_cash=10_000,
            max_position_ratio=1.0,
            commission_rate=0.0,
            transfer_fee_rate=0.0,
            stamp_duty_rate=0.0,
        ),
        strategy,
    )

    result = engine.run(bars, corporate_actions=corporate_actions)

    assert [fill.side for fill in result.fills] == ["BUY"]
    assert result.equity_curve[0] == pytest.approx(10_000.0)
    assert result.equity_curve[1] == pytest.approx(10_190.0)
    assert result.equity_curve[-1] == pytest.approx(10_190.0)


def test_forward_adjustment_transforms_pre_ex_bar_prices_for_research_view() -> None:
    bars = [
        MarketBar(symbol="AAA", date=date(2026, 1, 5), open=10.0, high=10.0, low=10.0, close=10.0, volume=10_000),
        MarketBar(symbol="AAA", date=date(2026, 1, 6), open=9.5, high=9.5, low=9.5, close=9.5, volume=10_000),
    ]
    action_book = CorporateActionBook(
        [CorporateAction(symbol="AAA", ex_date=date(2026, 1, 6), cash_dividend_per_share=0.5, share_ratio=0.0)]
    )

    adjusted = action_book.apply_forward_adjustments(bars)

    assert adjusted[0].close == pytest.approx(9.5)
    assert adjusted[1].close == pytest.approx(9.5)


def test_backtest_can_use_forward_adjusted_price_mode_with_raw_bars() -> None:
    start = date(2026, 1, 5)
    bars = [
        MarketBar(symbol="AAA", date=start, open=10.0, high=10.0, low=10.0, close=10.0, volume=10_000),
        MarketBar(symbol="AAA", date=start + timedelta(days=1), open=9.5, high=9.5, low=9.5, close=9.5, volume=10_000),
        MarketBar(symbol="AAA", date=start + timedelta(days=2), open=9.5, high=9.5, low=9.5, close=9.5, volume=10_000),
    ]
    corporate_actions = [CorporateAction(symbol="AAA", ex_date=start + timedelta(days=1), cash_dividend_per_share=0.5)]
    strategy = ExplicitOrderStrategy({("AAA", start + timedelta(days=1)): [Order(symbol="AAA", side="BUY", quantity=100)]})
    engine = BacktestEngine(
        AccountConfig(
            initial_cash=10_000,
            max_position_ratio=1.0,
            commission_rate=0.0,
            transfer_fee_rate=0.0,
            stamp_duty_rate=0.0,
            price_adjustment_mode="forward",
        ),
        strategy,
    )

    result = engine.run(bars, corporate_actions=corporate_actions)

    assert len(result.fills) == 1
    assert result.fills[0].price == pytest.approx(9.5)
    assert result.equity_curve[-1] == pytest.approx(10_000.0)


def test_forward_mode_uses_adjusted_signal_prices_but_raw_fill_prices() -> None:
    start = date(2026, 1, 5)
    bars = [
        MarketBar(symbol="AAA", date=start, open=12.0, high=12.0, low=12.0, close=12.0, volume=10_000),
        MarketBar(symbol="AAA", date=start + timedelta(days=1), open=10.0, high=10.0, low=10.0, close=10.0, volume=10_000),
        MarketBar(symbol="AAA", date=start + timedelta(days=2), open=5.0, high=5.0, low=5.0, close=5.0, volume=10_000),
    ]
    corporate_actions = [
        CorporateAction(symbol="AAA", ex_date=start + timedelta(days=2), cash_dividend_per_share=0.0, share_ratio=1.0)
    ]

    forward_engine = BacktestEngine(
        AccountConfig(
            initial_cash=10_000,
            max_position_ratio=1.0,
            commission_rate=0.0,
            transfer_fee_rate=0.0,
            stamp_duty_rate=0.0,
            price_adjustment_mode="forward",
        ),
        AdjustedPriceTriggerStrategy(trigger_price=5.0, trigger_bar_count=2),
    )
    raw_engine = BacktestEngine(
        AccountConfig(
            initial_cash=10_000,
            max_position_ratio=1.0,
            commission_rate=0.0,
            transfer_fee_rate=0.0,
            stamp_duty_rate=0.0,
            price_adjustment_mode="none",
        ),
        AdjustedPriceTriggerStrategy(trigger_price=5.0, trigger_bar_count=2),
    )

    forward_result = forward_engine.run(bars, corporate_actions=corporate_actions)
    raw_result = raw_engine.run(bars, corporate_actions=corporate_actions)

    assert len(forward_result.fills) == 1
    assert forward_result.fills[0].date == start + timedelta(days=1)
    assert forward_result.fills[0].price == pytest.approx(10.0)
    assert forward_result.equity_curve[-1] == pytest.approx(10_000.0)
    assert raw_result.fills == []
