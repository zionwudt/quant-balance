"""不依赖 httpx 的 API 集成冒烟测试。"""

from __future__ import annotations

import asyncio
import json
import math
from unittest.mock import patch
from urllib.parse import urlencode

import pandas as pd

from quant_balance.api.app import create_api_app
from quant_balance.core.backtest import OptimizeResult


def _make_sample_df(days: int = 240) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    close = [10 + math.sin(index / 8) * 2 + index * 0.02 for index in range(days)]
    return pd.DataFrame({
        "Open": close,
        "High": close,
        "Low": close,
        "Close": close,
        "Volume": [1_000_000] * days,
    }, index=dates)


async def _asgi_request(app, method: str, path: str, payload: dict | None = None) -> tuple[int, dict[str, str], object]:
    path_only, _, query_string = path.partition("?")
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    headers = [
        (b"host", b"testserver"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    if payload is not None:
        headers.append((b"content-type", b"application/json"))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path_only,
        "raw_path": path_only.encode("ascii"),
        "query_string": query_string.encode("ascii"),
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "root_path": "",
    }

    events = [{"type": "http.request", "body": body, "more_body": False}]
    response_status = 500
    response_headers: dict[str, str] = {}
    response_body = bytearray()

    async def receive():
        if events:
            return events.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal response_status
        if message["type"] == "http.response.start":
            response_status = message["status"]
            response_headers.update({
                key.decode("latin1"): value.decode("latin1")
                for key, value in message.get("headers", [])
            })
        elif message["type"] == "http.response.body":
            response_body.extend(message.get("body", b""))

    await app(scope, receive, send)
    content_type = response_headers.get("content-type", "")
    if not response_body:
        parsed = None
    elif "application/json" in content_type:
        parsed = json.loads(response_body.decode("utf-8"))
    else:
        parsed = response_body.decode("utf-8")
    return response_status, response_headers, parsed


def _request(app, method: str, path: str, payload: dict | None = None) -> tuple[int, dict[str, str], object]:
    return asyncio.run(_asgi_request(app, method, path, payload))


def test_api_http_smoke_end_to_end():
    sample_df = _make_sample_df()
    benchmark_df = sample_df.copy()
    benchmark_close = [10 + index * 0.01 for index in range(len(benchmark_df))]
    benchmark_df["Open"] = benchmark_close
    benchmark_df["High"] = benchmark_close
    benchmark_df["Low"] = benchmark_close
    benchmark_df["Close"] = benchmark_close
    optimize_result = OptimizeResult(
        best_stats=pd.Series({"Return [%]": 127.18, "Sharpe Ratio": 3.9, "# Trades": 4}),
        best_params={"fast_period": pd.Index([4])[0], "slow_period": pd.Index([18])[0]},
        top_results=[
            {
                "rank": 1,
                "score": 3.9,
                "params": {"fast_period": 4, "slow_period": 18},
                "stats": {"total_return_pct": 127.18, "sharpe_ratio": 3.9},
            }
        ],
        candidate_count=9,
    )

    def fake_load_dataframe(
        symbol: str,
        start_date: str,
        end_date: str,
        asset_type: str = "stock",
        adjust: str = "qfq",
        provider=None,
        db_path=None,
    ):
        df = benchmark_df.copy() if symbol == "000300.SH" else sample_df.copy()
        df.attrs["asset_type"] = asset_type
        df.attrs["data_provider"] = provider or "tushare"
        return df

    def fake_load_multi_dataframes(
        symbols,
        start_date: str,
        end_date: str,
        asset_type: str = "stock",
        adjust: str = "qfq",
        data_provider=None,
        db_path=None,
    ):
        payload = {}
        for symbol in symbols:
            df = sample_df.copy()
            df.attrs["asset_type"] = asset_type
            df.attrs["data_provider"] = data_provider or "tushare"
            payload[symbol] = df
        return payload

    with (
        patch("quant_balance.services.backtest_service.load_dataframe", side_effect=fake_load_dataframe),
        patch(
            "quant_balance.services.backtest_service.optimize",
            return_value=optimize_result,
        ),
        patch(
            "quant_balance.services.stock_pool_service.run_stock_pool_filter",
            return_value={
                "symbols": ["AAA"],
                "items": [
                    {
                        "ts_code": "AAA",
                        "name": "测试股",
                        "list_date": "20100101",
                        "delist_date": None,
                        "industry": "银行",
                        "market": "主板",
                        "listing_days": 5000,
                        "is_st": False,
                        "pe": 10.0,
                        "total_mv": 1_000_000.0,
                    }
                ],
                "total_count": 1,
                "run_context": {"pool_date": "2024-01-01", "filters": {"industries": ["银行"]}},
            },
        ),
        patch(
            "quant_balance.services.factor_service.run_factor_ranking",
            return_value={
                "symbols": ["AAA", "BBB"],
                "weights": {"roe": 0.6, "pe": 0.4},
                "rankings": [
                    {
                        "symbol": "AAA",
                        "name": "测试股A",
                        "industry": "银行",
                        "market": "主板",
                        "listing_days": 5000,
                        "ann_date": "20240110",
                        "end_date": "20231231",
                        "total_score": 88.0,
                        "rank": 1,
                        "factors": {
                            "roe": {"raw_value": 20.0, "score": 100.0, "weight": 0.6, "direction": "higher_better"},
                            "pe": {"raw_value": 10.0, "score": 70.0, "weight": 0.4, "direction": "lower_better"},
                        },
                    },
                    {
                        "symbol": "BBB",
                        "name": "测试股B",
                        "industry": "银行",
                        "market": "主板",
                        "listing_days": 4000,
                        "ann_date": "20240110",
                        "end_date": "20231231",
                        "total_score": 72.0,
                        "rank": 2,
                        "factors": {
                            "roe": {"raw_value": 15.0, "score": 70.0, "weight": 0.6, "direction": "higher_better"},
                            "pe": {"raw_value": 8.0, "score": 75.0, "weight": 0.4, "direction": "lower_better"},
                        },
                    },
                ],
                "run_context": {
                    "pool_date": "2024-01-01",
                    "pool_filters": {"industries": ["银行"]},
                    "candidate_count": 2,
                    "scored_count": 2,
                    "top_n": 2,
                    "skipped_symbols_no_financial": [],
                    "skipped_symbols_missing_factors": [],
                    "factors": [
                        {"name": "roe", "weight": 0.6, "direction": "higher_better"},
                        {"name": "pe", "weight": 0.4, "direction": "lower_better"},
                    ],
                },
            },
        ),
        patch(
            "quant_balance.scheduler.DailyScanScheduler.get_status",
            return_value={
                "enabled": True,
                "running": True,
                "apscheduler_available": True,
                "config": {
                    "scan_time": "16:00",
                    "strategies": ["macd", "rsi"],
                },
                "next_run_time": "2024-03-29T16:00:00+08:00",
                "last_scan": {
                    "scan_id": "scan-latest",
                    "status": "completed",
                    "signals_count": 2,
                },
            },
        ),
        patch(
            "quant_balance.scheduler.DailyScanScheduler.run_manual_scan",
            return_value={
                "scan_id": "scan-manual",
                "status": "completed",
                "requested_trade_date": "2024-03-29",
                "effective_trade_date": "2024-03-29",
                "signals_count": 2,
                "signals": [
                    {"symbol": "AAA", "strategy": "macd"},
                    {"symbol": "BBB", "strategy": "rsi"},
                ],
                "notifications": [],
            },
        ),
        patch(
            "quant_balance.core.signals.list_recent_signals",
            return_value=[
                {"symbol": "AAA", "strategy": "macd", "trade_date": "2024-03-29"},
                {"symbol": "BBB", "strategy": "rsi", "trade_date": "2024-03-29"},
            ],
        ),
        patch(
            "quant_balance.core.signals.list_today_signals",
            return_value={
                "date": "2024-03-29",
                "total": 2,
                "items": [
                    {"id": 1, "symbol": "AAA", "strategy": "macd", "status": "pending"},
                    {"id": 2, "symbol": "BBB", "strategy": "rsi", "status": "pending"},
                ],
            },
        ),
        patch(
            "quant_balance.core.signals.list_signal_history",
            return_value={
                "days": 30,
                "page": 1,
                "page_size": 2,
                "total": 2,
                "has_more": False,
                "items": [
                    {"id": 1, "symbol": "AAA", "strategy": "macd", "return_5d_pct": 3.2},
                    {"id": 2, "symbol": "BBB", "strategy": "rsi", "return_5d_pct": -1.4},
                ],
            },
        ),
        patch(
            "quant_balance.core.signals.update_signal_status",
            return_value={
                "id": 1,
                "symbol": "AAA",
                "strategy": "macd",
                "status": "executed",
            },
        ),
        patch(
            "quant_balance.notify.send_configured_notifications",
            return_value=[
                {"channel": "wecom", "status": "sent"},
                {"channel": "serverchan", "status": "failed", "detail": "bad webhook"},
            ],
        ),
        patch(
            "quant_balance.services.symbol_search_service.search_symbol_candidates",
            return_value=[
                {"symbol": "600519.SH", "name": "贵州茅台", "industry": "白酒", "market": "主板", "asset_type": "stock", "kind": "stock"},
                {"symbol": "000300.SH", "name": "沪深300", "market": "指数", "asset_type": "stock", "kind": "benchmark"},
            ],
        ),
        patch("quant_balance.services.portfolio_service.load_multi_dataframes", side_effect=fake_load_multi_dataframes),
        patch("quant_balance.services.screening_service.load_multi_dataframes", side_effect=fake_load_multi_dataframes),
        patch("quant_balance.services.screening_service.get_pool_at_date", return_value=["AAA", "BBB"]),
    ):
        app = create_api_app()

        root_status, root_headers, root_payload = _request(app, "GET", "/")
        assert root_status == 200
        assert "text/html" in root_headers.get("content-type", "")
        assert "/static/vendor/echarts.min.js" in root_payload
        assert "cdn.jsdelivr.net" not in root_payload
        assert 'data-page="stock-pool"' in root_payload
        assert 'data-page="paper-trading"' in root_payload
        assert 'data-page="signals"' in root_payload
        assert 'data-page="settings"' in root_payload
        assert "股票池筛选" in root_payload
        assert "模拟盘" in root_payload
        assert "信号中心" in root_payload
        assert "偏好与配置" in root_payload
        assert "qb-appearance" in root_payload
        assert "qb-rise-fall-style" in root_payload

        favicon_status, favicon_headers, favicon_payload = _request(app, "GET", "/favicon.svg")
        assert favicon_status == 200
        assert "image/svg+xml" in favicon_headers.get("content-type", "")
        assert "<svg" in favicon_payload

        scheduler_status, _, scheduler_status_payload = _request(app, "GET", "/api/scheduler/status")
        assert scheduler_status == 200
        assert scheduler_status_payload["enabled"] is True
        assert scheduler_status_payload["last_scan"]["status"] == "completed"

        scheduler_run_status, _, scheduler_run_payload = _request(
            app,
            "POST",
            "/api/scheduler/run",
            {
                "trade_date": "2024-03-29",
                "force": True,
            },
        )
        assert scheduler_run_status == 200
        assert scheduler_run_payload["status"] == "completed"
        assert scheduler_run_payload["signals_count"] == 2

        recent_signals_status, _, recent_signals_payload = _request(
            app,
            "GET",
            f"/api/signals/recent?{urlencode({'limit': 2, 'trade_date': '2024-03-29'})}",
        )
        assert recent_signals_status == 200
        assert len(recent_signals_payload["items"]) == 2
        assert recent_signals_payload["items"][0]["strategy"] == "macd"

        today_signals_status, _, today_signals_payload = _request(
            app,
            "GET",
            f"/api/signals/today?{urlencode({'limit': 20, 'date': '2024-03-29'})}",
        )
        assert today_signals_status == 200
        assert today_signals_payload["total"] == 2
        assert today_signals_payload["items"][0]["status"] == "pending"

        history_signals_status, _, history_signals_payload = _request(
            app,
            "GET",
            f"/api/signals/history?{urlencode({'days': 30, 'page': 1, 'page_size': 2})}",
        )
        assert history_signals_status == 200
        assert history_signals_payload["total"] == 2
        assert history_signals_payload["items"][1]["strategy"] == "rsi"

        signal_update_status, _, signal_update_payload = _request(
            app,
            "PATCH",
            "/api/signals/1",
            {"status": "executed"},
        )
        assert signal_update_status == 200
        assert signal_update_payload["status"] == "executed"

        notify_test_status, _, notify_test_payload = _request(
            app,
            "POST",
            "/api/notify/test",
            {
                "enabled": ["wecom", "serverchan"],
                "wecom_webhook": "https://example.com/wecom",
                "serverchan_sendkey": "sendkey",
            },
        )
        assert notify_test_status == 200
        assert notify_test_payload["success_count"] == 1
        assert notify_test_payload["failure_count"] == 1

        health_status, _, health_payload = _request(app, "GET", "/health")
        assert health_status == 200
        assert health_payload == {"status": "ok"}

        meta_status, _, meta_payload = _request(app, "GET", "/api/meta")
        assert meta_status == 200
        assert meta_payload["server_mode"] == "api"
        assert "sma_cross" in meta_payload["strategies"]
        assert "macd" in meta_payload["strategies"]
        assert "dca" in meta_payload["signals"]
        assert any(item["name"] == "roe" for item in meta_payload["factors"])
        assert meta_payload["defaults"]["factors_rank"]["factors"][0]["name"] == "roe"
        assert meta_payload["defaults"]["stock_pool"]["filters"]["exclude_st"] is False
        assert meta_payload["defaults"]["portfolio"]["allocation"] == "equal"

        strategies_status, _, strategies_payload = _request(app, "GET", "/api/strategies")
        assert strategies_status == 200
        strategy_names = {item["name"] for item in strategies_payload["strategies"]}
        signal_names = {item["name"] for item in strategies_payload["signals"]}
        assert {"sma_cross", "macd", "dca", "ma_rsi_filter"}.issubset(strategy_names)
        assert {"sma_cross", "macd", "dca", "ma_rsi_filter"}.issubset(signal_names)

        search_status, _, search_payload = _request(
            app,
            "GET",
            f"/api/symbols/search?{urlencode({'q': '茅台', 'limit': 5})}",
        )
        assert search_status == 200
        assert search_payload["query"] == "茅台"
        assert search_payload["items"][0]["symbol"] == "600519.SH"
        assert search_payload["items"][1]["kind"] == "benchmark"

        backtest_status, _, backtest_payload = _request(
            app,
            "POST",
            "/api/backtest/run",
            {
                "symbol": "AAA",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "strategy": "sma_cross",
                "cash": 100_000.0,
                "commission": 0.0,
                "benchmark_symbol": "000300.SH",
                "params": {
                    "fast_period": 5,
                    "slow_period": 20,
                    "stop_loss_pct": 0.05,
                    "take_profit_pct": 0.1,
                },
            },
        )
        assert backtest_status == 200
        assert backtest_payload["summary"]["initial_equity"] == 100_000.0
        assert backtest_payload["summary"]["stop_loss_pct"] == 0.05
        assert backtest_payload["summary"]["take_profit_pct"] == 0.1
        assert backtest_payload["summary"]["trades_count"] > 0
        assert "calmar_ratio" in backtest_payload["summary"]
        assert len(backtest_payload["summary"]["monthly_returns"]) > 0
        assert isinstance(backtest_payload["summary"]["rolling_sharpe"], list)
        assert len(backtest_payload["summary"]["yearly_stats"]) > 0
        assert backtest_payload["summary"]["benchmark_symbol"] == "000300.SH"
        assert len(backtest_payload["trades"]) > 0
        assert "stop_loss_price" in backtest_payload["trades"][0]
        assert "exit_reason" in backtest_payload["trades"][0]
        assert len(backtest_payload["equity_curve"]) > 0
        assert len(backtest_payload["price_bars"]) == len(sample_df)
        assert backtest_payload["price_bars"][0]["date"] == "2024-01-01"
        assert len(backtest_payload["chart_overlays"]["line_series"]) == 2
        assert len(backtest_payload["chart_overlays"]["trade_markers"]) >= 2
        assert "benchmark_equity" in backtest_payload["equity_curve"][0]
        assert "excess_return_pct" in backtest_payload["equity_curve"][0]
        assert backtest_payload["run_context"]["asset_type"] == "stock"
        assert backtest_payload["run_context"]["benchmark_symbol"] == "000300.SH"

        cb_backtest_status, _, cb_backtest_payload = _request(
            app,
            "POST",
            "/api/backtest/run",
            {
                "symbol": "110043.SH",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "asset_type": "convertible_bond",
                "strategy": "buy_and_hold",
                "cash": 100_000.0,
                "commission": 0.0,
            },
        )
        assert cb_backtest_status == 200
        assert cb_backtest_payload["run_context"]["asset_type"] == "convertible_bond"

        optimize_status, _, optimize_payload = _request(
            app,
            "POST",
            "/api/backtest/optimize",
            {
                "symbol": "AAA",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "strategy": "sma_cross",
                "cash": 100_000.0,
                "commission": 0.0,
                "maximize": "Return [%]",
                "param_ranges": {"fast_period": [4, 5, 6], "slow_period": [18, 20, 22]},
            },
        )
        assert optimize_status == 200
        assert optimize_payload["best_params"]["fast_period"] in [4, 5, 6]
        assert optimize_payload["best_params"]["slow_period"] in [18, 20, 22]
        assert optimize_payload["best_stats"]["total_return_pct"] > 0
        assert optimize_payload["top_results"][0]["rank"] == 1
        assert optimize_payload["execution"]["candidate_count"] == 9

        portfolio_status, _, portfolio_payload = _request(
            app,
            "POST",
            "/api/portfolio/run",
            {
                "symbols": ["AAA", "BBB"],
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "allocation": "custom",
                "weights": {"AAA": 0.6, "BBB": 0.4},
                "rebalance_frequency": "monthly",
                "cash": 100_000.0,
                "commission": 0.0,
            },
        )
        assert portfolio_status == 200
        assert portfolio_payload["summary"]["symbols_count"] == 2
        assert portfolio_payload["summary"]["allocation"] == "custom"
        assert portfolio_payload["summary"]["rebalance_frequency"] == "monthly"
        assert len(portfolio_payload["summary"]["monthly_returns"]) > 0
        assert len(portfolio_payload["summary"]["yearly_stats"]) > 0
        assert isinstance(portfolio_payload["summary"]["rolling_sharpe"], list)
        assert len(portfolio_payload["equity_curve"]) > 0
        assert len(portfolio_payload["weights"]) > 0
        assert len(portfolio_payload["rebalances"]) > 0

        stock_pool_status, _, stock_pool_payload = _request(
            app,
            "POST",
            "/api/stock-pool/filter",
            {
                "pool_date": "2024-01-01",
                "filters": {
                    "industries": ["银行"],
                    "exclude_st": True,
                },
                "symbols": ["AAA", "BBB"],
            },
        )
        assert stock_pool_status == 200
        assert stock_pool_payload["total_count"] == 1
        assert stock_pool_payload["symbols"] == ["AAA"]

        factors_status, _, factors_payload = _request(
            app,
            "POST",
            "/api/factors/rank",
            {
                "pool_date": "2024-01-01",
                "factors": [
                    {"name": "roe", "weight": 0.6},
                    {"name": "pe", "weight": 0.4},
                ],
                "pool_filters": {"industries": ["银行"]},
                "top_n": 2,
            },
        )
        assert factors_status == 200
        assert factors_payload["symbols"] == ["AAA", "BBB"]
        assert factors_payload["weights"]["roe"] == 0.6
        assert factors_payload["rankings"][0]["rank"] == 1

        screening_status, _, screening_payload = _request(
            app,
            "POST",
            "/api/screening/run",
            {
                "pool_date": "2024-01-01",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "signal": "sma_cross",
                "signal_params": {
                    "fast": 5,
                    "slow": 20,
                    "stop_loss_pct": 0.05,
                    "take_profit_pct": 0.1,
                },
                "top_n": 2,
                "cash": 100_000.0,
            },
        )
        assert screening_status == 200
        assert screening_payload["total_screened"] == 2
        assert len(screening_payload["rankings"]) == 2
        assert screening_payload["run_context"]["asset_type"] == "stock"

        cb_screening_status, _, cb_screening_payload = _request(
            app,
            "POST",
            "/api/screening/run",
            {
                "pool_date": "2024-01-01",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "asset_type": "convertible_bond",
                "signal": "sma_cross",
                "symbols": ["110043.SH", "113001.SH"],
                "top_n": 2,
                "cash": 100_000.0,
            },
        )
        assert cb_screening_status == 200
        assert cb_screening_payload["run_context"]["asset_type"] == "convertible_bond"
