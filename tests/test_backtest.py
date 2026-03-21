from datetime import date, timedelta

from quant_balance.backtest import BacktestEngine
from quant_balance.models import AccountConfig, MarketBar
from quant_balance.strategy import BuyAndHoldStrategy


def test_backtest_runs_for_a_share_lot_size() -> None:
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

    start = date(2026, 1, 1)
    bars = [
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

    result = engine.run(bars)

    assert result.halted is False
    assert len(result.fills) == 1
    assert result.fills[0].quantity % 100 == 0
    assert result.equity_curve[-1] > 0
