"""测试 API 路由装配和错误映射。"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from quant_balance.api.app import create_api_app
from quant_balance.api.schemas import BacktestRunRequest, ScreeningRunRequest


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
        ("/api/strategies", "GET"),
        ("/api/backtest/run", "POST"),
        ("/api/backtest/optimize", "POST"),
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
    assert result["defaults"]["backtest"]["strategy"] == "sma_cross"
    assert "sma_cross" in result["strategies"]


def test_post_routes_expose_request_body_in_openapi():
    schema = create_api_app().openapi()

    assert "requestBody" in schema["paths"]["/api/backtest/run"]["post"]
    assert "requestBody" in schema["paths"]["/api/backtest/optimize"]["post"]
    assert "requestBody" in schema["paths"]["/api/screening/run"]["post"]


def test_backtest_schema_requires_core_fields():
    with pytest.raises(ValidationError):
        BacktestRunRequest.model_validate({})


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
        strategy="sma_cross",
        cash=100_000.0,
        commission=0.001,
        params={"fast_period": 5},
    )


def test_backtest_run_maps_value_error_to_http_400():
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
