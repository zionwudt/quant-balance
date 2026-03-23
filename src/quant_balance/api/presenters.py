"""API 响应构建。"""

from __future__ import annotations

from dataclasses import dataclass
import json

from quant_balance.api.meta import get_backtest_field_guide
from quant_balance.core.report import BacktestReport


@dataclass(slots=True)
class BacktestResponse:
    """一次回测执行返回给前端的标准结构。"""

    summary: dict[str, float | int | str | None]
    closed_trades: list[dict[str, object]]
    assumptions: list[str]
    chart_sections: list[str]
    sample_size_warning: str | None = None
    run_context: dict[str, object] | None = None
    export_json: str | None = None
    equity_curve_points: list[dict[str, object]] | None = None


def build_backtest_response(
    report: BacktestReport,
    *,
    run_context: dict[str, object] | None = None,
    equity_curve_points: list[dict[str, object]] | None = None,
) -> BacktestResponse:
    """把回测报告转换成统一的 API 返回体。"""

    guide = get_backtest_field_guide()
    closed_trades = report.to_dict()["closed_trades"]
    summary: dict[str, float | int | str | None] = {
        "initial_equity": report.initial_equity,
        "final_equity": report.final_equity,
        "total_return_pct": report.total_return_pct,
        "annualized_return_pct": report.annualized_return_pct,
        "annualized_volatility_pct": report.annualized_volatility_pct,
        "sharpe_ratio": report.sharpe_ratio,
        "sortino_ratio": report.sortino_ratio,
        "max_drawdown_pct": report.max_drawdown_pct,
        "max_drawdown_start": report.max_drawdown_start.isoformat() if report.max_drawdown_start else None,
        "max_drawdown_end": report.max_drawdown_end.isoformat() if report.max_drawdown_end else None,
        "trades_count": report.trades_count,
        "win_rate_pct": report.win_rate_pct,
        "turnover_ratio": report.turnover_ratio,
        "benchmark_name": report.benchmark_name,
        "benchmark_return_pct": report.benchmark_return_pct,
        "excess_return_pct": report.excess_return_pct,
    }
    export_payload = {
        "summary": summary,
        "closed_trades": closed_trades,
        "run_context": run_context or {},
        "assumptions": guide.notes,
        "sample_size_warning": report.sample_size_warning,
    }
    return BacktestResponse(
        summary=summary,
        closed_trades=closed_trades,
        assumptions=guide.notes,
        chart_sections=["summary", "trades", "equity_curve", "run_context", "export"],
        sample_size_warning=report.sample_size_warning,
        run_context=run_context or {},
        export_json=json.dumps(export_payload, ensure_ascii=False, indent=2),
        equity_curve_points=equity_curve_points or [],
    )
