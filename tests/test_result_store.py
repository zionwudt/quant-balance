"""测试回测结果持久化与历史对比。"""

from __future__ import annotations

from pathlib import Path

import pytest

from quant_balance.data.result_store import (
    compare_backtest_runs,
    delete_backtest_run,
    get_backtest_run,
    list_backtest_runs,
    save_backtest_run,
)


def _sample_request(
    *,
    symbol: str = "600519.SH",
    strategy: str = "sma_cross",
    fast_period: int = 5,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "start_date": "2024-01-01",
        "end_date": "2024-06-30",
        "asset_type": "stock",
        "strategy": strategy,
        "cash": 100_000.0,
        "commission": 0.001,
        "slippage_mode": "off",
        "slippage_rate": 0.0,
        "params": {
            "fast_period": fast_period,
            "slow_period": 20,
        },
    }


def _sample_result(
    *,
    symbol: str = "600519.SH",
    strategy: str = "sma_cross",
    fast_period: int = 5,
    final_equity: float = 102_000.0,
    total_return_pct: float = 2.0,
) -> dict[str, object]:
    return {
        "summary": {
            "initial_equity": 100_000.0,
            "final_equity": final_equity,
            "total_return_pct": total_return_pct,
            "annualized_return_pct": 12.0,
            "sharpe_ratio": 1.5,
            "sortino_ratio": 1.8,
            "max_drawdown_pct": 1.0,
            "calmar_ratio": 12.0,
            "trades_count": 1,
            "win_rate_pct": 100.0,
            "profit_factor": 2.1,
        },
        "trades": [
            {
                "entry_time": "2024-01-01 00:00:00",
                "exit_time": "2024-01-02 00:00:00",
                "entry_price": 10.0,
                "exit_price": 10.2,
                "pnl": 20.0,
                "return_pct": 2.0,
            }
        ],
        "equity_curve": [
            {"date": "2024-01-01 00:00:00", "equity": 100_000.0},
            {"date": "2024-01-02 00:00:00", "equity": final_equity},
        ],
        "price_bars": [
            {"date": "2024-01-01", "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1, "volume": 1_000_000},
        ],
        "chart_overlays": {
            "line_series": [{"key": "sma_fast", "values": [{"date": "2024-01-01", "value": 10.0}]}],
            "trade_markers": [{"date": "2024-01-01", "side": "buy", "price": 10.0}],
        },
        "run_context": {
            "symbol": symbol,
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
            "asset_type": "stock",
            "strategy": strategy,
            "cash": 100_000.0,
            "commission": 0.001,
            "params": {
                "fast_period": fast_period,
                "slow_period": 20,
            },
            "bars_count": 120,
            "data_provider": "tushare",
        },
    }


def test_backtest_result_store_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "results.db"
    request_payload = _sample_request()
    result_payload = _sample_result()

    saved = save_backtest_run(
        request_payload=request_payload,
        result_payload=result_payload,
        db_path=db_path,
        run_id="run-1",
        created_at="2026-03-25T11:15:00+08:00",
    )

    assert saved["run_id"] == "run-1"

    history = list_backtest_runs(db_path=db_path)
    assert history["total"] == 1
    assert history["items"][0]["run_id"] == "run-1"
    assert history["items"][0]["params"]["fast_period"] == 5

    detail = get_backtest_run("run-1", db_path=db_path)
    assert detail["summary"]["final_equity"] == 102_000.0
    assert detail["trades"][0]["pnl"] == 20.0
    assert detail["equity_curve"][1]["equity"] == 102_000.0
    assert detail["price_bars"][0]["date"] == "2024-01-01"
    assert detail["chart_overlays"]["trade_markers"][0]["side"] == "buy"
    assert detail["run_context"]["symbol"] == "600519.SH"


def test_list_backtest_runs_supports_filters_and_pagination(tmp_path: Path) -> None:
    db_path = tmp_path / "results.db"
    save_backtest_run(
        request_payload=_sample_request(symbol="AAA", fast_period=5),
        result_payload=_sample_result(symbol="AAA", fast_period=5, final_equity=101_000.0),
        db_path=db_path,
        run_id="run-1",
        created_at="2026-03-20T10:00:00+08:00",
    )
    save_backtest_run(
        request_payload=_sample_request(symbol="AAA", fast_period=8),
        result_payload=_sample_result(symbol="AAA", fast_period=8, final_equity=104_000.0),
        db_path=db_path,
        run_id="run-2",
        created_at="2026-03-22T10:00:00+08:00",
    )
    save_backtest_run(
        request_payload=_sample_request(symbol="BBB", strategy="buy_and_hold"),
        result_payload=_sample_result(symbol="BBB", strategy="buy_and_hold", final_equity=99_000.0),
        db_path=db_path,
        run_id="run-3",
        created_at="2026-04-01T10:00:00+08:00",
    )

    first_page = list_backtest_runs(page=1, page_size=2, db_path=db_path)
    assert first_page["total"] == 3
    assert first_page["total_pages"] == 2
    assert [item["run_id"] for item in first_page["items"]] == ["run-3", "run-2"]

    filtered = list_backtest_runs(
        page=1,
        page_size=10,
        symbol="AAA",
        strategy="sma_cross",
        date_from="2026-03-21",
        date_to="2026-03-31",
        db_path=db_path,
    )
    assert filtered["total"] == 1
    assert filtered["items"][0]["run_id"] == "run-2"


def test_compare_backtest_runs_builds_metrics_and_param_diffs(tmp_path: Path) -> None:
    db_path = tmp_path / "results.db"
    save_backtest_run(
        request_payload=_sample_request(symbol="AAA", fast_period=5),
        result_payload=_sample_result(symbol="AAA", fast_period=5, final_equity=102_000.0, total_return_pct=2.0),
        db_path=db_path,
        run_id="run-1",
        created_at="2026-03-25T10:00:00+08:00",
    )
    save_backtest_run(
        request_payload=_sample_request(symbol="AAA", fast_period=9),
        result_payload=_sample_result(symbol="AAA", fast_period=9, final_equity=96_500.0, total_return_pct=-3.5),
        db_path=db_path,
        run_id="run-2",
        created_at="2026-03-25T11:00:00+08:00",
    )

    payload = compare_backtest_runs(["run-1", "run-2"], db_path=db_path)

    assert [item["run_id"] for item in payload["items"]] == ["run-1", "run-2"]
    assert payload["largest_spread_metric"] == "final_equity"
    assert payload["metrics"][0]["key"] == "final_equity"
    assert payload["metrics"][0]["is_largest_spread"] is True
    assert len(payload["equity_curves"]) == 2
    assert "params.fast_period" in payload["param_diffs"]["changed_keys"]
    assert payload["param_diffs"]["rows"][0]["is_different"] is True


def test_delete_backtest_run_removes_record(tmp_path: Path) -> None:
    db_path = tmp_path / "results.db"
    save_backtest_run(
        request_payload=_sample_request(),
        result_payload=_sample_result(),
        db_path=db_path,
        run_id="run-1",
        created_at="2026-03-25T11:15:00+08:00",
    )

    payload = delete_backtest_run("run-1", db_path=db_path)

    assert payload == {"run_id": "run-1", "deleted": True}
    assert list_backtest_runs(db_path=db_path)["total"] == 0
    with pytest.raises(LookupError, match="run-1"):
        get_backtest_run("run-1", db_path=db_path)
