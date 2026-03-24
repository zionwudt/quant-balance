"""测试股票池服务层编排。"""

from __future__ import annotations

from unittest.mock import patch

from quant_balance.data.stock_pool import StockPoolRecord
from quant_balance.services.stock_pool_service import run_stock_pool_filter


def test_run_stock_pool_filter_returns_api_ready_payload():
    records = [
        StockPoolRecord(
            ts_code="600519.SH",
            name="贵州茅台",
            list_date="20010827",
            delist_date=None,
            industry="白酒",
            market="主板",
            listing_days=8000,
            is_st=False,
            pe=28.0,
            total_mv=2_600_000.0,
        ),
    ]
    with patch("quant_balance.services.stock_pool_service.filter_pool_at_date", return_value=records) as mock_filter:
        payload = run_stock_pool_filter(
            pool_date="2024-01-01",
            filters={"industries": ["白酒"]},
            symbols=["600519.SH"],
        )

    assert payload["symbols"] == ["600519.SH"]
    assert payload["total_count"] == 1
    assert payload["items"][0]["industry"] == "白酒"
    mock_filter.assert_called_once_with(
        "2024-01-01",
        filters={"industries": ["白酒"]},
        symbols=["600519.SH"],
    )
