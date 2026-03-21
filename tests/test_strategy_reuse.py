from datetime import date, timedelta

from quant_balance.backtest import BacktestEngine
from quant_balance.models import AccountConfig, MarketBar
from quant_balance.strategy import BuyAndHoldStrategy


def _sample_bars() -> list[MarketBar]:
    start = date(2026, 1, 1)
    return [
        MarketBar(
            symbol="600519.SH",
            date=start + timedelta(days=index),
            open=10.0 + index,
            high=10.5 + index,
            low=9.5 + index,
            close=10.0 + index,
            volume=1_000_000,
        )
        for index in range(5)
    ]


def test_strategy_instance_can_be_reused_across_runs() -> None:
    config = AccountConfig(
        initial_cash=100_000,
        max_position_ratio=1.0,
        max_positions=5,
        commission_rate=0.0,
        transfer_fee_rate=0.0,
        stamp_duty_rate=0.0,
    )
    strategy = BuyAndHoldStrategy()
    engine = BacktestEngine(config=config, strategy=strategy)

    first = engine.run(_sample_bars())
    second = engine.run(_sample_bars())

    assert len(first.fills) == 1
    assert len(second.fills) == 1
    assert second.fills[0] == first.fills[0]


def test_backtest_results_are_deterministic_for_same_input() -> None:
    config = AccountConfig(
        initial_cash=100_000,
        max_position_ratio=1.0,
        max_positions=5,
        commission_rate=0.0,
        transfer_fee_rate=0.0,
        stamp_duty_rate=0.0,
    )
    strategy = BuyAndHoldStrategy()
    engine = BacktestEngine(config=config, strategy=strategy)
    bars = _sample_bars()

    first = engine.run(bars)
    second = engine.run(bars)

    assert second.equity_curve == first.equity_curve
    assert second.halted is first.halted
    assert second.fills == first.fills
