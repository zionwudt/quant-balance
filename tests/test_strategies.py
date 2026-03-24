"""测试策略定义。"""

import pandas as pd

from quant_balance.core.strategies import (
    BollingerBreakout,
    SIGNAL_REGISTRY,
    STRATEGY_REGISTRY,
    BuyAndHold,
    DcaStrategy,
    GridStrategy,
    MacdCross,
    MaRsiFilter,
    RsiStrategy,
    SmaCross,
    bollinger_signals,
    dca_signals,
    grid_signals,
    macd_signals,
    ma_rsi_filter_signals,
    sma_cross_signals,
    ema_cross_signals,
    rsi_signals,
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


def _make_close_df(close_values: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(close_values), freq="B")
    return pd.DataFrame({
        "Open": close_values,
        "High": [value * 1.01 for value in close_values],
        "Low": [value * 0.99 for value in close_values],
        "Close": close_values,
        "Volume": [1_000_000] * len(close_values),
    }, index=dates)


def test_strategy_registry_has_expected_keys():
    assert "sma_cross" in STRATEGY_REGISTRY
    assert "ema_cross" in STRATEGY_REGISTRY
    assert "buy_and_hold" in STRATEGY_REGISTRY
    assert "macd" in STRATEGY_REGISTRY
    assert "rsi" in STRATEGY_REGISTRY
    assert "bollinger" in STRATEGY_REGISTRY
    assert "grid" in STRATEGY_REGISTRY
    assert "dca" in STRATEGY_REGISTRY
    assert "ma_rsi_filter" in STRATEGY_REGISTRY


def test_registry_points_to_strategy_classes():
    assert STRATEGY_REGISTRY["sma_cross"] is SmaCross
    assert STRATEGY_REGISTRY["buy_and_hold"] is BuyAndHold
    assert STRATEGY_REGISTRY["macd"] is MacdCross
    assert STRATEGY_REGISTRY["rsi"] is RsiStrategy
    assert STRATEGY_REGISTRY["bollinger"] is BollingerBreakout
    assert STRATEGY_REGISTRY["grid"] is GridStrategy
    assert STRATEGY_REGISTRY["dca"] is DcaStrategy
    assert STRATEGY_REGISTRY["ma_rsi_filter"] is MaRsiFilter


def test_signal_registry_has_expected_keys():
    assert "sma_cross" in SIGNAL_REGISTRY
    assert "ema_cross" in SIGNAL_REGISTRY
    assert "macd" in SIGNAL_REGISTRY
    assert "rsi" in SIGNAL_REGISTRY
    assert "bollinger" in SIGNAL_REGISTRY
    assert "grid" in SIGNAL_REGISTRY
    assert "dca" in SIGNAL_REGISTRY
    assert "ma_rsi_filter" in SIGNAL_REGISTRY


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


def test_macd_signals_emit_entries_and_exits():
    close = [120 - index for index in range(25)]
    close += [95 + index * 1.5 for index in range(30)]
    close += [140 - index * 1.2 for index in range(25)]
    df = _make_close_df(close)

    entries, exits = macd_signals(df, fast_period=6, slow_period=13, signal_period=5)

    assert entries.dtype == bool
    assert exits.dtype == bool
    assert entries.any()
    assert exits.any()


def test_rsi_signals_emit_entries_and_exits():
    close = [120 - index * 2 for index in range(18)]
    close += [84 + index * 2.5 for index in range(24)]
    df = _make_close_df(close)

    entries, exits = rsi_signals(df, period=7, oversold=35, overbought=65)

    assert entries.dtype == bool
    assert exits.dtype == bool
    assert entries.any()
    assert exits.any()


def test_bollinger_signals_emit_entries_and_exits():
    close = [100.0] * 25
    close += [101.0, 102.0, 104.0, 108.0, 112.0, 116.0, 119.0, 121.0]
    close += [117.0, 112.0, 108.0, 103.0, 100.0, 98.0]
    df = _make_close_df(close)

    entries, exits = bollinger_signals(df, period=20, num_std=1.6)

    assert entries.dtype == bool
    assert exits.dtype == bool
    assert entries.any()
    assert exits.any()


def test_grid_signals_emit_entries_and_exits():
    close = [100.0] * 20
    close += [99.0, 97.0, 95.0, 92.0, 89.0, 88.0, 90.0, 95.0, 101.0, 107.0, 112.0]
    df = _make_close_df(close)

    entries, exits = grid_signals(df, anchor_period=10, grid_pct=0.05)

    assert entries.dtype == bool
    assert exits.dtype == bool
    assert entries.any()
    assert exits.any()


def test_dca_signals_follow_fixed_interval():
    df = _make_sample_df(45)

    entries, exits = dca_signals(df, interval_days=10, trade_fraction=0.25)

    assert entries.dtype == bool
    assert exits.dtype == bool
    assert entries.sum() == 5
    assert exits.sum() == 0
    assert entries.iloc[0]
    assert entries.iloc[10]
    assert entries.iloc[20]


def test_ma_rsi_filter_signals_emit_entries_and_exits():
    close = [100.0] * 18
    close += [101.0 + index * 1.8 for index in range(22)]
    close += [140.0 - index * 2.0 for index in range(14)]
    df = _make_close_df(close)

    entries, exits = ma_rsi_filter_signals(
        df,
        fast_period=5,
        slow_period=15,
        rsi_period=7,
        rsi_threshold=55,
        exit_rsi=45,
    )

    assert entries.dtype == bool
    assert exits.dtype == bool
    assert entries.any()
    assert exits.any()
