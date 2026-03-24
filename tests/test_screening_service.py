"""测试筛选服务层编排。"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from quant_balance.core.screening import ScreeningResult
from quant_balance.services.screening_service import run_stock_screening


def test_run_stock_screening_rejects_unknown_signal():
    with pytest.raises(ValueError, match="未知信号"):
        run_stock_screening(
            pool_date="2024-01-01",
            start_date="2024-01-01",
            end_date="2024-06-30",
            signal="unknown",
        )


def test_run_stock_screening_returns_empty_payload_when_no_data():
    with patch("quant_balance.services.screening_service.load_multi_dataframes", return_value={}):
        result = run_stock_screening(
            pool_date="2024-01-01",
            start_date="2024-01-01",
            end_date="2024-06-30",
            symbols=["AAA"],
        )

    assert result["rankings"] == []
    assert result["total_screened"] == 0


def test_run_stock_screening_uses_pool_and_top_n():
    rankings = pd.DataFrame(
        {
            "total_return": [15.0, 10.0],
            "sharpe_ratio": [1.5, 1.2],
        },
        index=["BBB", "AAA"],
    )
    result_obj = ScreeningResult(
        rankings=rankings,
        details={
            "AAA": {"total_return": 10.0},
            "BBB": {"total_return": 15.0},
        },
    )
    dummy_df = pd.DataFrame({"Close": [1, 2, 3]})

    with (
        patch("quant_balance.services.screening_service.get_pool_at_date", return_value=["AAA", "BBB"]) as mock_pool,
        patch("quant_balance.services.screening_service.load_multi_dataframes", return_value={"AAA": dummy_df, "BBB": dummy_df}) as mock_load,
        patch("quant_balance.services.screening_service.run_screening", return_value=result_obj) as mock_run,
    ):
        result = run_stock_screening(
            pool_date="2024-01-01",
            start_date="2024-01-01",
            end_date="2024-06-30",
            top_n=1,
        )

    assert result["total_screened"] == 2
    assert result["rankings"] == [{"symbol": "BBB", "total_return": 15.0, "sharpe_ratio": 1.5}]
    mock_pool.assert_called_once_with("2024-01-01")
    mock_load.assert_called_once()
    mock_run.assert_called_once()
