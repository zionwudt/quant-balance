"""测试筛选服务层编排。"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from quant_balance.core.screening import ScreeningResult
from quant_balance.services.screening_service import run_stock_screening
from quant_balance.data.stock_pool import StockPoolRecord


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


def test_run_stock_screening_passes_data_provider():
    dummy_df = pd.DataFrame({"Close": [1, 2, 3]})
    with (
        patch("quant_balance.services.screening_service.load_multi_dataframes", return_value={"AAA": dummy_df}) as mock_load,
        patch("quant_balance.services.screening_service.run_screening", return_value=ScreeningResult(rankings=pd.DataFrame(), details={})),
    ):
        result = run_stock_screening(
            pool_date="2024-01-01",
            start_date="2024-01-01",
            end_date="2024-06-30",
            symbols=["AAA"],
            data_provider="baostock",
        )

    assert result["run_context"]["data_provider"] == "baostock"
    mock_load.assert_called_once_with(
        ["AAA"],
        "2024-01-01",
        "2024-06-30",
        asset_type="stock",
        timeframe="1d",
        adjust="qfq",
        data_provider="baostock",
    )


def test_run_stock_screening_applies_pool_filters_before_loading_data():
    dummy_df = pd.DataFrame({"Close": [1, 2, 3]})
    filtered_records = [
        StockPoolRecord(
            ts_code="BBB",
            name="测试股",
            list_date="20100101",
            delist_date=None,
            industry="银行",
            market="主板",
            listing_days=5000,
            is_st=False,
        ),
    ]
    with (
        patch("quant_balance.services.screening_service.filter_pool_at_date", return_value=filtered_records) as mock_filter,
        patch("quant_balance.services.screening_service.load_multi_dataframes", return_value={"BBB": dummy_df}) as mock_load,
        patch("quant_balance.services.screening_service.run_screening", return_value=ScreeningResult(rankings=pd.DataFrame(), details={})),
    ):
        result = run_stock_screening(
            pool_date="2024-01-01",
            start_date="2024-01-01",
            end_date="2024-06-30",
            pool_filters={"industries": ["银行"], "exclude_st": True},
            symbols=["AAA", "BBB"],
        )

    assert result["run_context"]["pool_filters"] == {"industries": ["银行"], "exclude_st": True}
    mock_filter.assert_called_once_with(
        "2024-01-01",
        filters={"industries": ["银行"], "exclude_st": True},
        symbols=["AAA", "BBB"],
    )
    mock_load.assert_called_once_with(
        ["BBB"],
        "2024-01-01",
        "2024-06-30",
        asset_type="stock",
        timeframe="1d",
        adjust="qfq",
    )


def test_run_stock_screening_rejects_pool_filters_for_convertible_bond():
    with pytest.raises(ValueError, match="暂不支持 pool_filters"):
        run_stock_screening(
            pool_date="2024-01-01",
            start_date="2024-01-01",
            end_date="2024-06-30",
            asset_type="convertible_bond",
            pool_filters={"exclude_st": True},
            symbols=["110043.SH"],
        )


def test_run_stock_screening_requires_symbols_for_convertible_bond():
    with pytest.raises(ValueError, match="需要显式传入 symbols"):
        run_stock_screening(
            pool_date="2024-01-01",
            start_date="2024-01-01",
            end_date="2024-06-30",
            asset_type="convertible_bond",
        )


def test_run_stock_screening_passes_convertible_bond_asset_type():
    dummy_df = pd.DataFrame({"Close": [100, 101, 102]})
    with (
        patch("quant_balance.services.screening_service.load_multi_dataframes", return_value={"110043.SH": dummy_df}) as mock_load,
        patch("quant_balance.services.screening_service.run_screening", return_value=ScreeningResult(rankings=pd.DataFrame(), details={})),
    ):
        result = run_stock_screening(
            pool_date="2024-01-01",
            start_date="2024-01-01",
            end_date="2024-06-30",
            asset_type="convertible_bond",
            symbols=["110043.SH"],
        )

    assert result["run_context"]["asset_type"] == "convertible_bond"
    mock_load.assert_called_once_with(
        ["110043.SH"],
        "2024-01-01",
        "2024-06-30",
        asset_type="convertible_bond",
        timeframe="1d",
        adjust="qfq",
    )


def test_run_stock_screening_passes_minute_timeframe() -> None:
    dummy_df = pd.DataFrame({"Close": [1, 2, 3]})
    with (
        patch("quant_balance.services.screening_service.load_multi_dataframes", return_value={"AAA": dummy_df}) as mock_load,
        patch("quant_balance.services.screening_service.run_screening", return_value=ScreeningResult(rankings=pd.DataFrame(), details={})) as mock_run,
    ):
        result = run_stock_screening(
            pool_date="2024-01-01",
            start_date="2024-01-01 09:30:00",
            end_date="2024-01-01 15:00:00",
            timeframe="5min",
            symbols=["AAA"],
        )

    assert result["run_context"]["timeframe"] == "5min"
    mock_load.assert_called_once_with(
        ["AAA"],
        "2024-01-01 09:30:00",
        "2024-01-01 15:00:00",
        asset_type="stock",
        timeframe="5min",
        adjust="none",
    )
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["freq"] == "5min"


def test_run_stock_screening_rejects_minute_timeframe_for_convertible_bond() -> None:
    with pytest.raises(ValueError, match="仅支持 stock"):
        run_stock_screening(
            pool_date="2024-01-01",
            start_date="2024-01-01 09:30:00",
            end_date="2024-01-01 15:00:00",
            asset_type="convertible_bond",
            timeframe="1min",
            symbols=["110043.SH"],
        )


def test_run_stock_screening_rejects_non_tushare_data_provider_for_minute() -> None:
    with pytest.raises(ValueError, match="仅支持 tushare"):
        run_stock_screening(
            pool_date="2024-01-01",
            start_date="2024-01-01 09:30:00",
            end_date="2024-01-01 15:00:00",
            timeframe="1min",
            data_provider="akshare",
            symbols=["AAA"],
        )
