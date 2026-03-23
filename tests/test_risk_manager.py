from quant_balance.core.models import AccountConfig, Order, Portfolio, Position
from quant_balance.core.risk import RiskManager


def test_validate_order_rejects_invalid_quantity_and_price() -> None:
    manager = RiskManager(AccountConfig())
    portfolio = Portfolio(cash=10_000)

    assert manager.validate_order(Order(symbol="AAA", side="BUY", quantity=0), price=10.0, portfolio=portfolio) is False
    assert manager.validate_order(Order(symbol="AAA", side="BUY", quantity=100), price=0.0, portfolio=portfolio) is False
    assert manager.validate_order(Order(symbol="AAA", side="BUY", quantity=150), price=10.0, portfolio=portfolio) is False


def test_validate_order_rejects_buy_when_cash_or_position_ratio_exceeded() -> None:
    config = AccountConfig(initial_cash=10_000, max_position_ratio=0.2)
    manager = RiskManager(config)
    portfolio = Portfolio(cash=10_000)

    assert manager.validate_order(Order(symbol="AAA", side="BUY", quantity=300), price=10.0, portfolio=portfolio) is False
    assert manager.validate_order(
        Order(symbol="AAA", side="BUY", quantity=100),
        price=100.0,
        portfolio=portfolio,
        estimated_fee=1.0,
    ) is False


def test_validate_order_allows_adding_existing_symbol_when_max_positions_reached() -> None:
    config = AccountConfig(initial_cash=10_000, max_position_ratio=1.0, max_positions=1)
    manager = RiskManager(config)
    portfolio = Portfolio(cash=8_000, positions={"AAA": Position(symbol="AAA", quantity=100, avg_price=10.0)})

    assert manager.validate_order(Order(symbol="AAA", side="BUY", quantity=100), price=10.0, portfolio=portfolio) is True
    assert manager.validate_order(Order(symbol="BBB", side="BUY", quantity=100), price=10.0, portfolio=portfolio) is False


def test_validate_order_rejects_sell_without_position_or_when_overselling() -> None:
    manager = RiskManager(AccountConfig())
    portfolio = Portfolio(cash=10_000, positions={"AAA": Position(symbol="AAA", quantity=100, avg_price=10.0)})

    assert manager.validate_order(Order(symbol="BBB", side="SELL", quantity=100), price=10.0, portfolio=portfolio) is False
    assert manager.validate_order(Order(symbol="AAA", side="SELL", quantity=200), price=10.0, portfolio=portfolio) is False
    assert manager.validate_order(Order(symbol="AAA", side="SELL", quantity=100), price=10.0, portfolio=portfolio) is True


def test_drawdown_exceeded_treats_threshold_as_trigger() -> None:
    manager = RiskManager(AccountConfig(max_drawdown_ratio=0.1))

    assert manager.drawdown_exceeded(equity=90.0, peak_equity=100.0) is True
    assert manager.drawdown_exceeded(equity=90.1, peak_equity=100.0) is False
    assert manager.drawdown_exceeded(equity=100.0, peak_equity=0.0) is False
