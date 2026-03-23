"""共享回测服务。

这层负责把"输入参数 -> 回测执行 -> 可展示结果片段"串起来，
供 API 层和其他调用入口共同复用。
"""

from __future__ import annotations

from dataclasses import dataclass

from quant_balance.data import DataLoadError, load_bars
from quant_balance.core.backtest import BacktestEngine
from quant_balance.core.models import AccountConfig
from quant_balance.core.report import BacktestReport
from quant_balance.core.strategy import MovingAverageCrossStrategy
from quant_balance.services.backtest_inputs import BacktestInputError, BacktestRequest


@dataclass(slots=True)
class BacktestRunArtifacts:
    """一次回测执行后产出的标准结果片段。"""

    report: BacktestReport
    run_context: dict[str, object]
    equity_curve_points: list[dict[str, object]]


def run_moving_average_backtest(
    request: BacktestRequest,
) -> BacktestRunArtifacts:
    """执行一次均线回测，并返回 API 可直接消费的标准结果。"""

    request.validate()

    try:
        bars = load_bars(request.symbol, request.start_date, request.end_date)
    except DataLoadError as exc:
        raise BacktestInputError(str(exc)) from exc

    strategy = MovingAverageCrossStrategy(short_window=request.short_window, long_window=request.long_window)

    config = AccountConfig(
        initial_cash=request.initial_cash,
        max_position_ratio=1.0,
        max_positions=1,
        max_drawdown_ratio=1.0,
    )
    engine = BacktestEngine(config=config, strategy=strategy)
    result = engine.run(bars)
    if result.report is None:
        raise RuntimeError("回测未生成 report")

    run_context = {
        "symbol": request.symbol,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "initial_cash": request.initial_cash,
        "short_window": request.short_window,
        "long_window": request.long_window,
        "bars_count": len(bars),
        "date_range_start": bars[0].date.isoformat() if bars else None,
        "date_range_end": bars[-1].date.isoformat() if bars else None,
    }
    equity_curve_points = [
        {"date": equity_date.isoformat(), "equity": equity}
        for equity_date, equity in zip(result.equity_dates, result.equity_curve)
    ]
    return BacktestRunArtifacts(
        report=result.report,
        run_context=run_context,
        equity_curve_points=equity_curve_points,
    )
