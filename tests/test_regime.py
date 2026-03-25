"""测试市场状态识别器。"""

from __future__ import annotations

import pandas as pd

from quant_balance.core.regime import RegimeDetector


def _make_frame(close_values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": close_values,
            "High": close_values,
            "Low": close_values,
            "Close": close_values,
            "Volume": [1_000_000] * len(close_values),
        },
        index=pd.date_range("2024-01-01", periods=len(close_values), freq="B"),
    )


def test_regime_detector_detects_bull_market() -> None:
    detector = RegimeDetector(
        short_window=5,
        long_window=10,
        momentum_window=5,
        trend_threshold=0.01,
        momentum_threshold=0.02,
    )
    frame = _make_frame([100 + index * 2 for index in range(40)])

    assert detector.detect(frame) == "BULL"


def test_regime_detector_detects_bear_market() -> None:
    detector = RegimeDetector(
        short_window=5,
        long_window=10,
        momentum_window=5,
        trend_threshold=0.01,
        momentum_threshold=0.02,
    )
    frame = _make_frame([200 - index * 2 for index in range(40)])

    assert detector.detect(frame) == "BEAR"


def test_regime_detector_detects_sideways_market() -> None:
    detector = RegimeDetector(
        short_window=5,
        long_window=10,
        momentum_window=5,
        trend_threshold=0.02,
        momentum_threshold=0.04,
    )
    frame = _make_frame([100, 101, 100, 99, 101, 100, 99, 100, 101, 100] * 4)

    assert detector.detect(frame) == "SIDEWAYS"


def test_regime_detector_returns_regime_series() -> None:
    detector = RegimeDetector(
        short_window=5,
        long_window=10,
        momentum_window=5,
        trend_threshold=0.01,
        momentum_threshold=0.02,
    )
    frame = _make_frame([100 + index * 2 for index in range(30)])

    series = detector.detect_series(frame)

    assert len(series) == len(frame)
    assert series.iloc[-1] == "BULL"
