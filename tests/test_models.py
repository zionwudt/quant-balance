from quant_balance.core.models import Portfolio, Position


def test_portfolio_total_equity_uses_latest_prices_when_available() -> None:
    portfolio = Portfolio(
        cash=5_000,
        positions={
            "AAA": Position(symbol="AAA", quantity=100, avg_price=10.0),
            "BBB": Position(symbol="BBB", quantity=200, avg_price=20.0),
        },
    )

    equity = portfolio.total_equity({"AAA": 12.0, "BBB": 18.0})

    assert equity == 5_000 + 100 * 12.0 + 200 * 18.0


def test_portfolio_total_equity_falls_back_to_average_price() -> None:
    portfolio = Portfolio(
        cash=1_000,
        positions={"AAA": Position(symbol="AAA", quantity=100, avg_price=10.0)},
    )

    assert portfolio.total_equity() == 2_000.0
    assert portfolio.positions["AAA"].market_value == 1_000.0
