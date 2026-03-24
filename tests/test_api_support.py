"""测试 API 路由装配和错误映射。"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from quant_balance.api.app import create_api_app
from quant_balance.api.schemas import (
    BacktestRunRequest,
    FactorsRankRequest,
    OptimizeConstraintRequest,
    OptimizeRequest,
    PortfolioRunRequest,
    ScreeningRunRequest,
    StockPoolFilterRequest,
    TushareTokenRequest,
    WalkForwardRequest,
)


def _get_route_endpoint(app, path: str, method: str):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError(f"未找到路由 {method} {path}")


def test_create_api_app_registers_expected_routes():
    app = create_api_app()

    expected_routes = {
        ("/health", "GET"),
        ("/api/meta", "GET"),
        ("/api/config/status", "GET"),
        ("/api/config/tushare-token", "POST"),
        ("/api/strategies", "GET"),
        ("/api/factors/rank", "POST"),
        ("/api/stock-pool/filter", "POST"),
        ("/api/backtest/run", "POST"),
        ("/api/backtest/optimize", "POST"),
        ("/api/portfolio/run", "POST"),
        ("/api/screening/run", "POST"),
    }
    actual_routes = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method != "HEAD"
    }

    assert expected_routes.issubset(actual_routes)


def test_health_endpoint_returns_ok():
    app = create_api_app()
    endpoint = _get_route_endpoint(app, "/health", "GET")

    assert endpoint() == {"status": "ok"}


def test_meta_endpoint_includes_defaults():
    app = create_api_app()
    endpoint = _get_route_endpoint(app, "/api/meta", "GET")

    result = endpoint()

    assert result["server_mode"] == "api"
    assert result["defaults"]["backtest"]["asset_type"] == "stock"
    assert result["defaults"]["backtest"]["strategy"] == "sma_cross"
    assert result["defaults"]["factors_rank"]["factors"][0]["name"] == "roe"
    assert result["defaults"]["stock_pool"]["filters"]["exclude_st"] is False
    assert result["defaults"]["portfolio"]["allocation"] == "equal"
    assert any(item["name"] == "roe" for item in result["factors"])
    assert "sma_cross" in result["strategies"]
    assert "macd" in result["strategies"]
    assert "dca" in result["strategies"]


def test_post_routes_expose_request_body_in_openapi():
    schema = create_api_app().openapi()

    assert "requestBody" in schema["paths"]["/api/factors/rank"]["post"]
    assert "requestBody" in schema["paths"]["/api/stock-pool/filter"]["post"]
    assert "requestBody" in schema["paths"]["/api/backtest/run"]["post"]
    assert "requestBody" in schema["paths"]["/api/backtest/optimize"]["post"]
    assert "requestBody" in schema["paths"]["/api/portfolio/run"]["post"]
    assert "requestBody" in schema["paths"]["/api/screening/run"]["post"]
    assert "requestBody" in schema["paths"]["/api/config/tushare-token"]["post"]


def test_backtest_schema_requires_core_fields():
    with pytest.raises(ValidationError):
        BacktestRunRequest.model_validate({})


def test_optimize_constraint_schema_requires_single_right_operand():
    with pytest.raises(ValidationError):
        OptimizeConstraintRequest.model_validate({
            "left": "fast_period",
            "operator": "<",
        })


def test_config_status_endpoint_returns_status():
    expected = {
        "config_exists": True,
        "config_path": "/tmp/config.toml",
        "token_configured": True,
        "token_placeholder": False,
        "connection_checked": True,
        "connection_ok": True,
        "register_url": "https://tushare.pro/register",
        "message": "Tushare token 验证成功。",
    }
    with patch("quant_balance.data.common.get_tushare_config_status", return_value=expected):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/config/status", "GET")

        result = endpoint()

    assert result == expected


def test_tushare_token_endpoint_validates_and_saves():
    base_status = {
        "config_exists": True,
        "config_path": "/tmp/config.toml",
        "token_configured": True,
        "token_placeholder": False,
        "connection_checked": False,
        "connection_ok": None,
        "register_url": "https://tushare.pro/register",
        "message": "Tushare token 已配置，尚未验证连接。",
    }
    with (
        patch("quant_balance.data.common.validate_tushare_token", return_value=(True, "ok")) as mock_validate,
        patch("quant_balance.data.common.save_tushare_token") as mock_save,
        patch("quant_balance.data.common.get_tushare_config_status", return_value=base_status.copy()) as mock_status,
    ):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/config/tushare-token", "POST")
        request = TushareTokenRequest(token="abc123")

        result = endpoint(request)

    assert result["saved"] is True
    assert result["connection_ok"] is True
    assert result["validate_only"] is False
    assert result["message"] == "Tushare token 已保存。"
    mock_validate.assert_called_once_with("abc123")
    mock_save.assert_called_once_with("abc123")
    mock_status.assert_called_once_with(check_connection=False)


def test_tushare_token_endpoint_supports_validate_only():
    base_status = {
        "config_exists": False,
        "config_path": "/tmp/config.toml",
        "token_configured": False,
        "token_placeholder": False,
        "connection_checked": False,
        "connection_ok": None,
        "register_url": "https://tushare.pro/register",
        "message": "未找到 config/config.toml。",
    }
    with (
        patch("quant_balance.data.common.validate_tushare_token", return_value=(True, "ok")) as mock_validate,
        patch("quant_balance.data.common.save_tushare_token") as mock_save,
        patch("quant_balance.data.common.get_tushare_config_status", return_value=base_status.copy()),
    ):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/config/tushare-token", "POST")
        request = TushareTokenRequest(token="abc123", validate_only=True)

        result = endpoint(request)

    assert result["saved"] is False
    assert result["validate_only"] is True
    assert result["message"] == "Tushare token 验证成功。"
    mock_validate.assert_called_once_with("abc123")
    mock_save.assert_not_called()


def test_backtest_run_delegates_to_service():
    payload = {"summary": {"final_equity": 123456.0}}
    with patch("quant_balance.services.backtest_service.run_single_backtest", return_value=payload) as mock_run:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/backtest/run", "POST")
        request = BacktestRunRequest(
            symbol="600519.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            strategy="sma_cross",
            cash=100_000.0,
            commission=0.001,
            params={"fast_period": 5},
        )

        result = endpoint(request)

    assert result == payload
    mock_run.assert_called_once_with(
        symbol="600519.SH",
        start_date="2024-01-01",
        end_date="2024-06-30",
        asset_type="stock",
        strategy="sma_cross",
        cash=100_000.0,
        commission=0.001,
        params={"fast_period": 5},
    )


def test_backtest_run_maps_value_error_to_http_400(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.WARNING, logger="quant_balance")
    with patch("quant_balance.services.backtest_service.run_single_backtest", side_effect=ValueError("未知策略")):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/backtest/run", "POST")
        request = BacktestRunRequest(
            symbol="600519.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            strategy="nonexistent",
        )

        with pytest.raises(HTTPException) as excinfo:
            endpoint(request)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "未知策略"
    records = [
        record for record in caplog.records
        if getattr(record, "qb_event", None) == "API_ERROR"
    ]
    assert len(records) == 1
    payload = records[0].qb_payload
    assert payload["endpoint"] == "/api/backtest/run"
    assert payload["status_code"] == 400
    assert payload["symbol"] == "600519.SH"


def test_backtest_run_delegates_convertible_bond_asset_type():
    payload = {"summary": {"final_equity": 123456.0}}
    with patch("quant_balance.services.backtest_service.run_single_backtest", return_value=payload) as mock_run:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/backtest/run", "POST")
        request = BacktestRunRequest(
            symbol="110043.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            asset_type="convertible_bond",
        )

        result = endpoint(request)

    assert result == payload
    mock_run.assert_called_once_with(
        symbol="110043.SH",
        start_date="2024-01-01",
        end_date="2024-06-30",
        asset_type="convertible_bond",
        strategy="sma_cross",
        cash=100_000.0,
        commission=0.001,
        params={},
    )


def test_backtest_optimize_delegates_enhanced_fields_to_service():
    payload = {"best_params": {"fast_period": 5, "slow_period": 20}}
    with patch("quant_balance.services.backtest_service.run_optimize", return_value=payload) as mock_run:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/backtest/optimize", "POST")
        request = OptimizeRequest(
            symbol="600519.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            strategy="sma_cross",
            cash=100_000.0,
            commission=0.001,
            maximize="Sharpe Ratio",
            param_ranges={"fast_period": [5, 6], "slow_period": [20, 30]},
            top_n=3,
            constraints=[OptimizeConstraintRequest(left="fast_period", operator="<", right_param="slow_period")],
            walk_forward=WalkForwardRequest(train_bars=60, test_bars=20, step_bars=20),
        )

        result = endpoint(request)

    assert result == payload
    mock_run.assert_called_once_with(
        symbol="600519.SH",
        start_date="2024-01-01",
        end_date="2024-06-30",
        asset_type="stock",
        strategy="sma_cross",
        cash=100_000.0,
        commission=0.001,
        maximize="Sharpe Ratio",
        param_ranges={"fast_period": [5, 6], "slow_period": [20, 30]},
        top_n=3,
        constraints=[{"left": "fast_period", "operator": "<", "right_param": "slow_period"}],
        walk_forward={"train_bars": 60, "test_bars": 20, "step_bars": 20, "anchored": False},
    )


def test_screening_run_maps_value_error_to_http_400():
    with patch("quant_balance.services.screening_service.run_stock_screening", side_effect=ValueError("未知信号")):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/screening/run", "POST")
        request = ScreeningRunRequest(
            pool_date="2024-01-01",
            start_date="2024-01-01",
            end_date="2024-06-30",
            signal="nonexistent",
        )

        with pytest.raises(HTTPException) as excinfo:
            endpoint(request)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "未知信号"


def test_factors_rank_delegates_to_service():
    payload = {"symbols": ["AAA"], "rankings": []}
    with patch("quant_balance.services.factor_service.run_factor_ranking", return_value=payload) as mock_run:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/factors/rank", "POST")
        request = FactorsRankRequest(
            pool_date="2024-01-01",
            factors=[
                {"name": "roe", "weight": 0.6},
                {"name": "pe", "weight": 0.4},
            ],
            pool_filters={"industries": ["银行"]},
            top_n=10,
            symbols=["AAA", "BBB"],
        )

        result = endpoint(request)

    assert result == payload
    mock_run.assert_called_once_with(
        pool_date="2024-01-01",
        factors=[
            {"name": "roe", "weight": 0.6},
            {"name": "pe", "weight": 0.4},
        ],
        pool_filters={"industries": ["银行"]},
        top_n=10,
        symbols=["AAA", "BBB"],
    )


def test_factors_rank_maps_value_error_to_http_400():
    with patch("quant_balance.services.factor_service.run_factor_ranking", side_effect=ValueError("未知因子")):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/factors/rank", "POST")
        request = FactorsRankRequest(pool_date="2024-01-01", factors=[{"name": "roe"}])

        with pytest.raises(HTTPException) as excinfo:
            endpoint(request)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "未知因子"


def test_screening_run_delegates_pool_filters_to_service():
    payload = {"rankings": [], "total_screened": 0}
    with patch("quant_balance.services.screening_service.run_stock_screening", return_value=payload) as mock_run:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/screening/run", "POST")
        request = ScreeningRunRequest(
            pool_date="2024-01-01",
            start_date="2024-01-01",
            end_date="2024-06-30",
            signal="sma_cross",
            pool_filters={"industries": ["银行"], "exclude_st": True},
            symbols=["AAA", "BBB"],
        )

        result = endpoint(request)

    assert result == payload
    mock_run.assert_called_once_with(
        pool_date="2024-01-01",
        start_date="2024-01-01",
        end_date="2024-06-30",
        asset_type="stock",
        signal="sma_cross",
        signal_params={},
        pool_filters={"industries": ["银行"], "exclude_st": True},
        top_n=20,
        cash=100_000.0,
        symbols=["AAA", "BBB"],
    )


def test_screening_run_delegates_convertible_bond_asset_type():
    payload = {"rankings": [], "total_screened": 0}
    with patch("quant_balance.services.screening_service.run_stock_screening", return_value=payload) as mock_run:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/screening/run", "POST")
        request = ScreeningRunRequest(
            pool_date="2024-01-01",
            start_date="2024-01-01",
            end_date="2024-06-30",
            asset_type="convertible_bond",
            signal="sma_cross",
            symbols=["110043.SH", "113001.SH"],
        )

        result = endpoint(request)

    assert result == payload
    mock_run.assert_called_once_with(
        pool_date="2024-01-01",
        start_date="2024-01-01",
        end_date="2024-06-30",
        asset_type="convertible_bond",
        signal="sma_cross",
        signal_params={},
        pool_filters={},
        top_n=20,
        cash=100_000.0,
        symbols=["110043.SH", "113001.SH"],
    )


def test_stock_pool_filter_delegates_to_service():
    payload = {"symbols": ["600519.SH"], "total_count": 1}
    with patch("quant_balance.services.stock_pool_service.run_stock_pool_filter", return_value=payload) as mock_run:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/stock-pool/filter", "POST")
        request = StockPoolFilterRequest(
            pool_date="2024-01-01",
            filters={"industries": ["白酒"], "exclude_st": True},
            symbols=["600519.SH"],
        )

        result = endpoint(request)

    assert result == payload
    mock_run.assert_called_once_with(
        pool_date="2024-01-01",
        filters={"industries": ["白酒"], "exclude_st": True},
        symbols=["600519.SH"],
    )


def test_portfolio_run_delegates_to_service():
    payload = {"summary": {"final_equity": 123456.0}}
    with patch("quant_balance.services.portfolio_service.run_portfolio_research", return_value=payload) as mock_run:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/portfolio/run", "POST")
        request = PortfolioRunRequest(
            symbols=["AAA", "BBB"],
            start_date="2024-01-01",
            end_date="2024-06-30",
            allocation="custom",
            weights={"AAA": 0.6, "BBB": 0.4},
            rebalance_frequency="monthly",
            cash=100_000.0,
            commission=0.001,
        )

        result = endpoint(request)

    assert result == payload
    mock_run.assert_called_once_with(
        symbols=["AAA", "BBB"],
        start_date="2024-01-01",
        end_date="2024-06-30",
        allocation="custom",
        weights={"AAA": 0.6, "BBB": 0.4},
        rebalance_frequency="monthly",
        cash=100_000.0,
        commission=0.001,
    )


def test_portfolio_run_maps_value_error_to_http_400():
    with patch("quant_balance.services.portfolio_service.run_portfolio_research", side_effect=ValueError("bad weights")):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/portfolio/run", "POST")
        request = PortfolioRunRequest(
            symbols=["AAA", "BBB"],
            start_date="2024-01-01",
            end_date="2024-06-30",
        )

        with pytest.raises(HTTPException) as excinfo:
            endpoint(request)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "bad weights"


def test_tushare_token_endpoint_maps_invalid_token_to_http_400(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.WARNING, logger="quant_balance")
    with patch("quant_balance.data.common.validate_tushare_token", return_value=(False, "bad token")):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/config/tushare-token", "POST")
        request = TushareTokenRequest(token="invalid")

        with pytest.raises(HTTPException) as excinfo:
            endpoint(request)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "bad token"
    records = [
        record for record in caplog.records
        if getattr(record, "qb_event", None) == "API_ERROR"
    ]
    assert len(records) == 1
    payload = records[0].qb_payload
    assert payload["endpoint"] == "/api/config/tushare-token"
    assert payload["status_code"] == 400


def test_backtest_run_maps_unexpected_error_to_http_500(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.ERROR, logger="quant_balance")
    with patch("quant_balance.services.backtest_service.run_single_backtest", side_effect=RuntimeError("boom")):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/backtest/run", "POST")
        request = BacktestRunRequest(
            symbol="600519.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            strategy="sma_cross",
        )

        with pytest.raises(HTTPException) as excinfo:
            endpoint(request)

    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == "内部服务器错误"
    records = [
        record for record in caplog.records
        if getattr(record, "qb_event", None) == "API_ERROR"
    ]
    assert len(records) == 1
    payload = records[0].qb_payload
    assert payload["endpoint"] == "/api/backtest/run"
    assert payload["status_code"] == 500
    assert payload["error_type"] == "RuntimeError"
