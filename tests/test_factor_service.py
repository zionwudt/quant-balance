"""测试多因子服务层编排。"""

from __future__ import annotations

from unittest.mock import patch

from quant_balance.data.fundamental_loader import FinancialSnapshot
from quant_balance.data.stock_pool import StockPoolRecord
from quant_balance.services.factor_service import run_factor_ranking


def test_run_factor_ranking_returns_api_ready_payload():
    records = [
        StockPoolRecord(
            ts_code="AAA",
            name="甲公司",
            list_date="20100101",
            delist_date=None,
            industry="银行",
            market="主板",
            listing_days=5000,
            is_st=False,
        ),
        StockPoolRecord(
            ts_code="BBB",
            name="乙公司",
            list_date="20100101",
            delist_date=None,
            industry="银行",
            market="主板",
            listing_days=5000,
            is_st=False,
        ),
    ]
    snapshots = {
        "AAA": FinancialSnapshot("AAA", "20240110", "20231231", roe=20.0, pe=10.0, pb=1.2, dv_ratio=1.5),
        "BBB": FinancialSnapshot("BBB", "20240110", "20231231", roe=15.0, pe=8.0, pb=1.0, dv_ratio=1.0),
    }

    with (
        patch("quant_balance.services.factor_service.filter_pool_at_date", return_value=records) as mock_pool,
        patch("quant_balance.services.factor_service.load_financial_at", side_effect=lambda symbol, pool_date: snapshots[symbol]) as mock_financial,
    ):
        payload = run_factor_ranking(
            pool_date="2024-01-15",
            factors=[
                {"name": "roe", "weight": 0.6},
                {"name": "pe", "weight": 0.4},
            ],
            top_n=1,
            pool_filters={"industries": ["银行"]},
        )

    assert payload["symbols"] == ["AAA"]
    assert payload["rankings"][0]["symbol"] == "AAA"
    assert payload["rankings"][0]["factors"]["roe"]["weight"] == 0.6
    assert payload["run_context"]["candidate_count"] == 2
    assert payload["run_context"]["scored_count"] == 2
    mock_pool.assert_called_once_with(
        "2024-01-15",
        filters={"industries": ["银行"]},
        symbols=None,
        data_provider=None,
    )
    assert mock_financial.call_count == 2


def test_run_factor_ranking_tracks_symbols_without_financial_snapshot():
    records = [
        StockPoolRecord(
            ts_code="AAA",
            name="甲公司",
            list_date="20100101",
            delist_date=None,
            industry="银行",
            market="主板",
            listing_days=5000,
            is_st=False,
        ),
    ]

    with (
        patch("quant_balance.services.factor_service.filter_pool_at_date", return_value=records),
        patch("quant_balance.services.factor_service.load_financial_at", return_value=None),
    ):
        payload = run_factor_ranking(
            pool_date="2024-01-15",
            factors=[{"name": "roe", "weight": 1.0}],
        )

    assert payload["rankings"] == []
    assert payload["run_context"]["skipped_symbols_no_financial"] == ["AAA"]


def test_run_factor_ranking_skips_when_market_regime_filter_mismatches():
    with (
        patch(
            "quant_balance.services.factor_service.resolve_market_regime_filter",
            return_value={
                "requested_regime": "BULL",
                "actual_regime": "BEAR",
                "matches": False,
                "symbol": "000300.SH",
                "date": "2024-01-15",
            },
        ) as mock_regime,
        patch("quant_balance.services.factor_service.filter_pool_at_date") as mock_pool,
        patch("quant_balance.services.factor_service.load_financial_at") as mock_financial,
    ):
        payload = run_factor_ranking(
            pool_date="2024-01-15",
            market_regime="BULL",
        )

    assert payload["rankings"] == []
    assert payload["run_context"]["market_regime_actual"] == "BEAR"
    assert payload["run_context"]["market_regime_match"] is False
    mock_regime.assert_called_once_with(
        "BULL",
        as_of_date="2024-01-15",
        symbol="000300.SH",
    )
    mock_pool.assert_not_called()
    mock_financial.assert_not_called()
