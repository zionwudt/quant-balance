"""不依赖 httpx 的 API 集成冒烟测试。"""

from __future__ import annotations

import asyncio
import json
import math
from unittest.mock import patch

import pandas as pd

from quant_balance.api.app import create_api_app


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
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
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
    parsed = json.loads(response_body.decode("utf-8")) if response_body else None
    return response_status, response_headers, parsed


def _request(app, method: str, path: str, payload: dict | None = None) -> tuple[int, dict[str, str], object]:
    return asyncio.run(_asgi_request(app, method, path, payload))


def test_api_http_smoke_end_to_end():
    sample_df = _make_sample_df()
    optimize_stats = pd.Series({"Return [%]": 127.18, "Sharpe Ratio": 3.9, "# Trades": 4})

    def fake_load_dataframe(symbol: str, start_date: str, end_date: str, adjust: str = "qfq", db_path=None):
        return sample_df.copy()

    def fake_load_multi_dataframes(symbols, start_date: str, end_date: str, adjust: str = "qfq", db_path=None):
        return {symbol: sample_df.copy() for symbol in symbols}

    with (
        patch("quant_balance.services.backtest_service.load_dataframe", side_effect=fake_load_dataframe),
        patch(
            "quant_balance.services.backtest_service.optimize",
            return_value=(optimize_stats, {"fast_period": pd.Index([4])[0], "slow_period": pd.Index([18])[0]}),
        ),
        patch("quant_balance.services.screening_service.load_multi_dataframes", side_effect=fake_load_multi_dataframes),
        patch("quant_balance.services.screening_service.get_pool_at_date", return_value=["AAA", "BBB"]),
    ):
        app = create_api_app()

        health_status, _, health_payload = _request(app, "GET", "/health")
        assert health_status == 200
        assert health_payload == {"status": "ok"}

        meta_status, _, meta_payload = _request(app, "GET", "/api/meta")
        assert meta_status == 200
        assert meta_payload["server_mode"] == "api"
        assert "sma_cross" in meta_payload["strategies"]
        assert "macd" in meta_payload["strategies"]
        assert "dca" in meta_payload["signals"]

        strategies_status, _, strategies_payload = _request(app, "GET", "/api/strategies")
        assert strategies_status == 200
        strategy_names = {item["name"] for item in strategies_payload["strategies"]}
        signal_names = {item["name"] for item in strategies_payload["signals"]}
        assert {"sma_cross", "macd", "dca", "ma_rsi_filter"}.issubset(strategy_names)
        assert {"sma_cross", "macd", "dca", "ma_rsi_filter"}.issubset(signal_names)

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
        assert len(backtest_payload["trades"]) > 0
        assert "stop_loss_price" in backtest_payload["trades"][0]
        assert "exit_reason" in backtest_payload["trades"][0]
        assert len(backtest_payload["equity_curve"]) > 0

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
