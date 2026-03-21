from datetime import date, timedelta

import pytest

from quant_balance.backtest import BacktestEngine
from quant_balance.models import AccountConfig, Fill, MarketBar, Order, Portfolio
from quant_balance.report import generate_report
from quant_balance.strategy import Strategy


class RoundTripStrategy(Strategy):
    name = "round-trip-strategy"

    def __init__(self, order_plan: dict[tuple[str, date], list[Order]]) -> None:
        self.order_plan = order_plan

    def generate_orders(self, bars: list[MarketBar], portfolio: Portfolio) -> list[Order]:
        latest = bars[-1]
        return self.order_plan.get((latest.symbol, latest.date), [])


def test_generate_report_computes_drawdown_and_trade_metrics() -> None:
    start = date(2026, 1, 1)
    config = AccountConfig(
        initial_cash=10_000,
        max_position_ratio=1.0,
        max_positions=5,
        commission_rate=0.0,
        transfer_fee_rate=0.0,
        stamp_duty_rate=0.0,
    )
    strategy = RoundTripStrategy(
        {
            ("AAA", start): [Order(symbol="AAA", side="BUY", quantity=100)],
            ("AAA", start + timedelta(days=2)): [Order(symbol="AAA", side="SELL", quantity=100)],
            ("AAA", start + timedelta(days=3)): [Order(symbol="AAA", side="BUY", quantity=100)],
            ("AAA", start + timedelta(days=5)): [Order(symbol="AAA", side="SELL", quantity=100)],
        }
    )
    engine = BacktestEngine(config=config, strategy=strategy)
    bars = [
        MarketBar(symbol="AAA", date=start, open=10.0, high=10.0, low=10.0, close=10.0, volume=1_000),
        MarketBar(symbol="AAA", date=start + timedelta(days=1), open=11.0, high=11.0, low=11.0, close=11.0, volume=1_000),
        MarketBar(symbol="AAA", date=start + timedelta(days=2), open=12.0, high=12.0, low=12.0, close=12.0, volume=1_000),
        MarketBar(symbol="AAA", date=start + timedelta(days=3), open=12.0, high=12.0, low=12.0, close=12.0, volume=1_000),
        MarketBar(symbol="AAA", date=start + timedelta(days=4), open=9.0, high=9.0, low=9.0, close=9.0, volume=1_000),
        MarketBar(symbol="AAA", date=start + timedelta(days=5), open=9.0, high=9.0, low=9.0, close=9.0, volume=1_000),
    ]

    result = engine.run(bars)

    assert result.report is not None
    assert result.report.final_equity == 9_900.0
    assert result.report.total_return_pct == pytest.approx(-1.0)
    assert result.report.max_drawdown_pct == pytest.approx(2.9411764706, rel=1e-6)
    assert result.report.max_drawdown_start == start + timedelta(days=2)
    assert result.report.max_drawdown_end == start + timedelta(days=4)
    assert result.report.trades_count == 2
    assert result.report.fills_count == 4
    assert result.report.win_rate_pct == pytest.approx(50.0)
    assert result.report.profit_loss_ratio == pytest.approx(2 / 3)
    assert result.report.average_holding_days == pytest.approx(2.0)
    assert result.report.turnover_ratio == pytest.approx(0.43)


def test_generate_report_supports_benchmark_comparison() -> None:
    report = generate_report(
        initial_equity=100.0,
        equity_curve=[100.0, 110.0, 105.0],
        equity_dates=[date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
        fills=[],
        benchmark_name="CSI300",
        benchmark_equity_curve=[100.0, 102.0, 101.0],
    )

    assert report.benchmark_name == "CSI300"
    assert report.benchmark_return_pct == pytest.approx(1.0)
    assert report.excess_return_pct == pytest.approx(4.0)


def test_report_to_dict_returns_json_ready_dates() -> None:
    report = generate_report(
        initial_equity=100.0,
        equity_curve=[100.0, 110.0, 105.0],
        equity_dates=[date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
        fills=[],
    )

    payload = report.to_dict()

    assert payload["max_drawdown_start"] == "2026-01-02"
    assert payload["max_drawdown_end"] == "2026-01-03"
    assert payload["closed_trades"] == []


def test_report_to_dict_serializes_closed_trade_dates() -> None:
    fills = [
        Fill(symbol="AAA", side="BUY", quantity=100, price=10.0, date=date(2026, 1, 1)),
        Fill(symbol="AAA", side="SELL", quantity=100, price=11.0, date=date(2026, 1, 3)),
    ]
    report = generate_report(
        initial_equity=1_000.0,
        equity_curve=[1_000.0, 1_050.0, 1_100.0],
        equity_dates=[date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
        fills=fills,
    )

    payload = report.to_dict()

    assert payload["closed_trades"][0]["entry_date"] == "2026-01-01"
    assert payload["closed_trades"][0]["exit_date"] == "2026-01-03"
