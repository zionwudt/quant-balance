from datetime import date, timedelta

from quant_balance.backtest import BacktestEngine
from quant_balance.models import AccountConfig, Fill, MarketBar, Order, Portfolio
from quant_balance.strategy import Strategy


class StaggeredMultiAssetStrategy(Strategy):
    name = "staggered-multi-asset"

    def __init__(self) -> None:
        self._submitted: set[tuple[str, date]] = set()

    def generate_orders(self, bars: list[MarketBar], portfolio: Portfolio) -> list[Order]:
        latest = bars[-1]
        key = (latest.symbol, latest.date)
        if key in self._submitted:
            return []

        order: Order | None = None
        if latest.symbol == "AAA" and latest.date == date(2026, 1, 1):
            order = Order(symbol="AAA", side="BUY", quantity=100)
        elif latest.symbol == "BBB" and latest.date == date(2026, 1, 2):
            order = Order(symbol="BBB", side="BUY", quantity=100)

        if order is None:
            return []

        self._submitted.add(key)
        return [order]


def test_backtest_marks_multi_asset_portfolio_to_market_with_latest_snapshot() -> None:
    config = AccountConfig(
        initial_cash=10_000,
        max_position_ratio=1.0,
        max_positions=5,
        commission_rate=0.0,
        transfer_fee_rate=0.0,
        stamp_duty_rate=0.0,
    )
    engine = BacktestEngine(config=config, strategy=StaggeredMultiAssetStrategy())

    start = date(2026, 1, 1)
    bars = [
        MarketBar(symbol="AAA", date=start, open=10.0, high=10.0, low=10.0, close=10.0, volume=1_000),
        MarketBar(symbol="BBB", date=start + timedelta(days=1), open=20.0, high=20.0, low=20.0, close=20.0, volume=1_000),
        MarketBar(symbol="AAA", date=start + timedelta(days=2), open=12.0, high=12.0, low=12.0, close=12.0, volume=1_000),
    ]

    result = engine.run(bars)

    assert result.fills == [
        Fill(symbol="AAA", side="BUY", quantity=100, price=10.0),
        Fill(symbol="BBB", side="BUY", quantity=100, price=20.0),
    ]
    assert result.equity_curve == [10_000.0, 10_000.0, 10_200.0]


def test_backtest_drawdown_uses_latest_snapshot_for_all_open_positions() -> None:
    config = AccountConfig(
        initial_cash=10_000,
        max_position_ratio=1.0,
        max_positions=5,
        max_drawdown_ratio=0.025,
        commission_rate=0.0,
        transfer_fee_rate=0.0,
        stamp_duty_rate=0.0,
    )
    engine = BacktestEngine(config=config, strategy=StaggeredMultiAssetStrategy())

    start = date(2026, 1, 1)
    bars = [
        MarketBar(symbol="AAA", date=start, open=10.0, high=10.0, low=10.0, close=10.0, volume=1_000),
        MarketBar(symbol="BBB", date=start + timedelta(days=1), open=20.0, high=20.0, low=20.0, close=20.0, volume=1_000),
        MarketBar(symbol="AAA", date=start + timedelta(days=2), open=12.0, high=12.0, low=12.0, close=12.0, volume=1_000),
        MarketBar(symbol="BBB", date=start + timedelta(days=3), open=21.0, high=21.0, low=21.0, close=21.0, volume=1_000),
        MarketBar(symbol="AAA", date=start + timedelta(days=4), open=10.0, high=10.0, low=10.0, close=10.0, volume=1_000),
    ]

    result = engine.run(bars)

    assert result.equity_curve == [10_000.0, 10_000.0, 10_200.0, 10_300.0, 10_100.0]
    assert result.halted is False
