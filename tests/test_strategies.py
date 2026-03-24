"""测试策略定义。"""

import pandas as pd

from quant_balance.core.strategies import (
    SIGNAL_REGISTRY,
    STRATEGY_REGISTRY,
    BuyAndHold,
    SmaCross,
    sma_cross_signals,
    ema_cross_signals,
)


def _make_sample_df(days: int = 100) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    close = [10.0 + index * 0.1 for index in range(days)]
    return pd.DataFrame({
        "Open": [value - 0.05 for value in close],
        "High": [value + 0.1 for value in close],
        "Low": [value - 0.1 for value in close],
        "Close": close,
        "Volume": [1_000_000] * days,
    }, index=dates)


def test_strategy_registry_has_expected_keys():
    assert "sma_cross" in STRATEGY_REGISTRY
    assert "ema_cross" in STRATEGY_REGISTRY
    assert "buy_and_hold" in STRATEGY_REGISTRY


def test_registry_points_to_strategy_classes():
    assert STRATEGY_REGISTRY["sma_cross"] is SmaCross
    assert STRATEGY_REGISTRY["buy_and_hold"] is BuyAndHold


def test_signal_registry_has_expected_keys():
    assert "sma_cross" in SIGNAL_REGISTRY
    assert "ema_cross" in SIGNAL_REGISTRY


def test_sma_cross_signals_returns_boolean_series():
    df = _make_sample_df()
    entries, exits = sma_cross_signals(df, fast=5, slow=20)

    assert isinstance(entries, pd.Series)
    assert isinstance(exits, pd.Series)
    assert entries.dtype == bool
    assert exits.dtype == bool
    assert len(entries) == len(df)


def test_ema_cross_signals_returns_boolean_series():
    df = _make_sample_df()
    entries, exits = ema_cross_signals(df, fast=12, slow=26)

    assert isinstance(entries, pd.Series)
    assert isinstance(exits, pd.Series)
    assert entries.dtype == bool
    assert exits.dtype == bool
    assert len(exits) == len(df)
