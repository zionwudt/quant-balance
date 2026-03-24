"""测试 vectorbt 批量筛选引擎。"""

import pandas as pd
import pytest

from quant_balance.core.screening import ScreeningResult, run_screening
from quant_balance.core.strategies import sma_cross_signals


def _make_sample_df(days: int = 100, base_price: float = 10.0) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    close = [base_price + index * 0.1 for index in range(days)]
    return pd.DataFrame({
        "Open": [value - 0.05 for value in close],
        "High": [value + 0.1 for value in close],
        "Low": [value - 0.1 for value in close],
        "Close": close,
        "Volume": [1_000_000] * days,
    }, index=dates)


def test_run_screening_returns_result():
    data = {
        "AAA": _make_sample_df(100, 10.0),
        "BBB": _make_sample_df(100, 20.0),
    }

    result = run_screening(data, sma_cross_signals, cash=100_000.0)

    assert isinstance(result, ScreeningResult)
    assert not result.rankings.empty
    assert len(result.details) == 2
    assert "total_return" in result.rankings.columns


def test_run_screening_empty_data():
    result = run_screening({}, sma_cross_signals)

    assert isinstance(result, ScreeningResult)
    assert result.rankings.empty
    assert len(result.details) == 0
