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
    NotifyTestRequest,
    OptimizeConstraintRequest,
    OptimizeRequest,
    PortfolioRunRequest,
    SchedulerRunRequest,
    SignalStatusUpdateRequest,
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
        ("/", "GET"),
        ("/favicon.svg", "GET"),
        ("/health", "GET"),
        ("/api/meta", "GET"),
        ("/api/config/status", "GET"),
        ("/api/scheduler/status", "GET"),
        ("/api/signals/recent", "GET"),
        ("/api/signals/today", "GET"),
        ("/api/signals/history", "GET"),
        ("/api/config/tushare-token", "POST"),
        ("/api/notify/test", "POST"),
        ("/api/scheduler/run", "POST"),
        ("/api/signals/{signal_id}", "PATCH"),
        ("/api/strategies", "GET"),
        ("/api/symbols/search", "GET"),
        ("/api/factors/rank", "POST"),
        ("/api/stock-pool/filter", "POST"),
        ("/api/backtest/run", "POST"),
        ("/api/backtest/history", "GET"),
        ("/api/backtest/history/{run_id}", "GET"),
        ("/api/backtest/history/{run_id}", "DELETE"),
        ("/api/backtest/compare", "GET"),
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
    assert "requestBody" in schema["paths"]["/api/notify/test"]["post"]
    assert "requestBody" in schema["paths"]["/api/scheduler/run"]["post"]
    assert "requestBody" in schema["paths"]["/api/signals/{signal_id}"]["patch"]


def test_backtest_schema_requires_core_fields():
    with pytest.raises(ValidationError):
        BacktestRunRequest.model_validate({})


def test_backtest_schema_rejects_orphan_benchmark_options():
    with pytest.raises(ValidationError):
        BacktestRunRequest.model_validate({
            "symbol": "600519.SH",
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
            "benchmark_asset_type": "stock",
        })


def test_symbols_search_delegates_to_service():
    payload = {
        "query": "茅台",
        "items": [{"symbol": "600519.SH", "name": "贵州茅台", "kind": "stock"}],
    }
    with patch(
        "quant_balance.services.symbol_search_service.search_symbol_candidates",
        return_value=payload["items"],
    ) as mock_search:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/symbols/search", "GET")

        result = endpoint("茅台", 5)

    assert result == payload
    mock_search.assert_called_once_with("茅台", limit=5)


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


def test_scheduler_status_endpoint_delegates_to_manager():
    expected = {
        "enabled": True,
        "running": True,
        "apscheduler_available": True,
        "config": {"scan_time": "16:00"},
        "next_run_time": "2024-03-29T16:00:00+08:00",
        "last_scan": {"status": "completed"},
    }
    with patch("quant_balance.scheduler.DailyScanScheduler.get_status", return_value=expected):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/scheduler/status", "GET")

        result = endpoint()

    assert result == expected


def test_scheduler_run_endpoint_delegates_to_manager():
    payload = {"status": "completed", "signals_count": 3}
    with patch("quant_balance.scheduler.DailyScanScheduler.run_manual_scan", return_value=payload) as mock_run:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/scheduler/run", "POST")
        request = SchedulerRunRequest(trade_date="2024-03-29", force=True)

        result = endpoint(request)

    assert result == payload
    mock_run.assert_called_once_with(trade_date="2024-03-29", force=True)


def test_signals_recent_endpoint_delegates_to_store():
    payload = [{"symbol": "AAA", "strategy": "macd"}]
    with patch("quant_balance.core.signals.list_recent_signals", return_value=payload) as mock_list:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/signals/recent", "GET")

        result = endpoint(10, "2024-03-29")

    assert result == {"items": payload}
    mock_list.assert_called_once_with(limit=10, trade_date="2024-03-29")


def test_signals_today_endpoint_delegates_to_store():
    payload = {
        "date": "2024-03-29",
        "total": 1,
        "items": [{"symbol": "AAA", "strategy": "macd"}],
    }
    with patch("quant_balance.core.signals.list_today_signals", return_value=payload) as mock_list:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/signals/today", "GET")

        result = endpoint(50, "2024-03-29")

    assert result == payload
    mock_list.assert_called_once_with(limit=50, as_of_date="2024-03-29")


def test_signals_history_endpoint_delegates_to_store():
    payload = {
        "days": 30,
        "page": 2,
        "page_size": 10,
        "total": 12,
        "has_more": False,
        "items": [{"symbol": "AAA", "strategy": "macd"}],
    }
    with patch("quant_balance.core.signals.list_signal_history", return_value=payload) as mock_list:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/signals/history", "GET")

        result = endpoint(30, 2, 10)

    assert result == payload
    mock_list.assert_called_once_with(days=30, page=2, page_size=10)


def test_signal_update_endpoint_delegates_to_store():
    payload = {"id": 12, "status": "executed"}
    with patch("quant_balance.core.signals.update_signal_status", return_value=payload) as mock_update:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/signals/{signal_id}", "PATCH")
        request = SignalStatusUpdateRequest(status="executed")

        result = endpoint(12, request)

    assert result == payload
    mock_update.assert_called_once_with(12, status="executed")


def test_notify_test_endpoint_delegates_to_notify_module():
    payload = {
        "items": [{"channel": "wecom", "status": "sent"}],
        "success_count": 1,
        "failure_count": 0,
    }
    with patch(
        "quant_balance.notify.send_configured_notifications",
        return_value=payload["items"],
    ) as mock_send:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/notify/test", "POST")
        request = NotifyTestRequest(
            enabled=["wecom"],
            wecom_webhook="https://example.com/wecom",
        )

        result = endpoint(request)

    assert result == payload
    mock_send.assert_called_once()


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
    with (
        patch("quant_balance.services.backtest_service.run_single_backtest", return_value=payload) as mock_run,
        patch("quant_balance.data.result_store.save_backtest_run") as mock_save,
    ):
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
    mock_save.assert_called_once()
    assert mock_save.call_args.kwargs["result_payload"] == payload
    assert mock_save.call_args.kwargs["request_payload"]["symbol"] == "600519.SH"


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
    with (
        patch("quant_balance.services.backtest_service.run_single_backtest", return_value=payload) as mock_run,
        patch("quant_balance.data.result_store.save_backtest_run") as mock_save,
    ):
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
    mock_save.assert_called_once()


def test_backtest_run_delegates_benchmark_fields_to_service():
    payload = {"summary": {"final_equity": 123456.0}}
    with (
        patch("quant_balance.services.backtest_service.run_single_backtest", return_value=payload) as mock_run,
        patch("quant_balance.data.result_store.save_backtest_run") as mock_save,
    ):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/backtest/run", "POST")
        request = BacktestRunRequest(
            symbol="600519.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            benchmark_symbol="000300.SH",
            benchmark_asset_type="stock",
            benchmark_data_provider="baostock",
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
        params={},
        benchmark_symbol="000300.SH",
        benchmark_asset_type="stock",
        benchmark_data_provider="baostock",
    )
    mock_save.assert_called_once()


def test_backtest_run_delegates_slippage_fields_to_service():
    payload = {"summary": {"final_equity": 123456.0}}
    with (
        patch("quant_balance.services.backtest_service.run_single_backtest", return_value=payload) as mock_run,
        patch("quant_balance.data.result_store.save_backtest_run") as mock_save,
    ):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/backtest/run", "POST")
        request = BacktestRunRequest(
            symbol="600519.SH",
            start_date="2024-01-01",
            end_date="2024-06-30",
            slippage_mode="spread",
            slippage_rate=0.002,
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
        params={},
        slippage_mode="spread",
        slippage_rate=0.002,
    )
    mock_save.assert_called_once()


def test_backtest_history_delegates_to_result_store():
    payload = {
        "items": [],
        "page": 2,
        "page_size": 10,
        "total": 0,
        "total_pages": 0,
        "filters": {
            "symbol": "600519.SH",
            "strategy": "sma_cross",
            "date_from": "2024-01-01",
            "date_to": "2024-01-31",
        },
    }
    with patch("quant_balance.data.result_store.list_backtest_runs", return_value=payload) as mock_list:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/backtest/history", "GET")

        result = endpoint(
            page=2,
            page_size=10,
            symbol="600519.SH",
            strategy="sma_cross",
            date_from="2024-01-01",
            date_to="2024-01-31",
        )

    assert result == payload
    mock_list.assert_called_once_with(
        page=2,
        page_size=10,
        symbol="600519.SH",
        strategy="sma_cross",
        date_from="2024-01-01",
        date_to="2024-01-31",
    )


def test_backtest_history_detail_delegates_to_result_store():
    payload = {
        "run_id": "run-1",
        "summary": {"final_equity": 123456.0},
        "trades": [],
        "equity_curve": [],
        "run_context": {"symbol": "600519.SH"},
    }
    with patch("quant_balance.data.result_store.get_backtest_run", return_value=payload) as mock_get:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/backtest/history/{run_id}", "GET")

        result = endpoint("run-1")

    assert result == payload
    mock_get.assert_called_once_with("run-1")


def test_backtest_compare_delegates_to_result_store():
    payload = {
        "items": [{"run_id": "run-1"}, {"run_id": "run-2"}],
        "metrics": [],
        "largest_spread_metric": None,
        "equity_curves": [],
        "param_diffs": {"rows": [], "all_keys": [], "changed_keys": []},
    }
    with patch("quant_balance.data.result_store.compare_backtest_runs", return_value=payload) as mock_compare:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/backtest/compare", "GET")

        result = endpoint("run-1, run-2")

    assert result == payload
    mock_compare.assert_called_once_with(["run-1", "run-2"])


def test_backtest_history_delete_delegates_to_result_store():
    payload = {"run_id": "run-1", "deleted": True}
    with patch("quant_balance.data.result_store.delete_backtest_run", return_value=payload) as mock_delete:
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/backtest/history/{run_id}", "DELETE")

        result = endpoint("run-1")

    assert result == payload
    mock_delete.assert_called_once_with("run-1")


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


def test_scheduler_run_maps_value_error_to_http_400():
    with patch("quant_balance.scheduler.DailyScanScheduler.run_manual_scan", side_effect=ValueError("bad scan")):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/scheduler/run", "POST")
        request = SchedulerRunRequest()

        with pytest.raises(HTTPException) as excinfo:
            endpoint(request)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "bad scan"


def test_signal_update_maps_lookup_error_to_http_404():
    with patch("quant_balance.core.signals.update_signal_status", side_effect=LookupError("signal missing")):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/signals/{signal_id}", "PATCH")
        request = SignalStatusUpdateRequest(status="ignored")

        with pytest.raises(HTTPException) as excinfo:
            endpoint(99, request)

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "signal missing"


def test_notify_test_maps_value_error_to_http_400():
    with patch("quant_balance.notify.send_configured_notifications", side_effect=ValueError("bad notify")):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/notify/test", "POST")
        request = NotifyTestRequest(enabled=["wecom"], wecom_webhook="https://example.com/wecom")

        with pytest.raises(HTTPException) as excinfo:
            endpoint(request)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "bad notify"


def test_backtest_history_detail_maps_lookup_error_to_http_404():
    with patch("quant_balance.data.result_store.get_backtest_run", side_effect=LookupError("run missing")):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/backtest/history/{run_id}", "GET")

        with pytest.raises(HTTPException) as excinfo:
            endpoint("run-404")

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "run missing"


def test_backtest_compare_maps_value_error_to_http_400():
    with patch("quant_balance.data.result_store.compare_backtest_runs", side_effect=ValueError("ids invalid")):
        app = create_api_app()
        endpoint = _get_route_endpoint(app, "/api/backtest/compare", "GET")

        with pytest.raises(HTTPException) as excinfo:
            endpoint("run-1")

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "ids invalid"


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
