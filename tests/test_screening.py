"""测试 vectorbt 批量筛选引擎。"""

import logging

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


def test_run_screening_emits_structured_log(caplog: pytest.LogCaptureFixture):
    data = {
        "AAA": _make_sample_df(100, 10.0),
        "BBB": _make_sample_df(100, 20.0),
    }
    caplog.set_level(logging.INFO, logger="quant_balance")

    run_screening(
        data,
        sma_cross_signals,
        log_context={
            "pool_date": "2024-01-01",
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
            "signal": "sma_cross",
        },
    )

    records = [
        record for record in caplog.records
        if getattr(record, "qb_event", None) == "SCREENING_RUN"
    ]
    assert len(records) == 1
    payload = records[0].qb_payload
    assert payload["stage"] == "engine"
    assert payload["signal"] == "sma_cross"
    assert payload["total_screened"] == 2
