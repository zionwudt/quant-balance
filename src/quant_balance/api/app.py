"""FastAPI 应用 — 回测与筛选接口。"""

from __future__ import annotations

from typing import Any

from quant_balance import __version__
from quant_balance.api.schemas import BacktestRunRequest, OptimizeRequest, ScreeningRunRequest
from quant_balance.core.strategies import SIGNAL_REGISTRY, STRATEGY_REGISTRY

WEB_DEPENDENCY_HINT = "启动 API 模式需要先安装项目依赖：pip install -e ."


def create_api_app() -> Any:
    """创建 FastAPI 应用。"""

    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:
        raise RuntimeError(WEB_DEPENDENCY_HINT) from exc

    from quant_balance.api.meta import build_api_meta
    from quant_balance.data.tushare_loader import DataLoadError
    from quant_balance.services.backtest_service import run_optimize, run_single_backtest
    from quant_balance.services.screening_service import run_stock_screening

    app = FastAPI(
        title="QuantBalance API",
        version=__version__,
        description="QuantBalance 回测与研究接口 — backtesting.py + vectorbt",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/meta")
    def api_meta() -> dict[str, object]:
        """返回前端初始化所需的元信息。"""
        return build_api_meta()

    @app.get("/api/strategies")
    def list_strategies() -> dict[str, object]:
        """返回可用的策略和信号函数列表。"""
        return {
            "strategies": [
                {"name": name, "doc": cls.__doc__ or ""}
                for name, cls in STRATEGY_REGISTRY.items()
            ],
            "signals": [
                {"name": name, "doc": func.__doc__ or ""}
                for name, func in SIGNAL_REGISTRY.items()
            ],
        }

    @app.post("/api/backtest/run")
    def backtest_run(req: BacktestRunRequest) -> dict:
        """单股精细回测。"""
        try:
            return run_single_backtest(
                symbol=req.symbol,
                start_date=req.start_date,
                end_date=req.end_date,
                strategy=req.strategy,
                cash=req.cash,
                commission=req.commission,
                params=req.params,
            )
        except (ValueError, DataLoadError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/backtest/optimize")
    def backtest_optimize(req: OptimizeRequest) -> dict:
        """参数优化。"""
        try:
            return run_optimize(
                symbol=req.symbol,
                start_date=req.start_date,
                end_date=req.end_date,
                strategy=req.strategy,
                cash=req.cash,
                commission=req.commission,
                maximize=req.maximize,
                param_ranges=req.param_ranges,
            )
        except (ValueError, DataLoadError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/screening/run")
    def screening_run(req: ScreeningRunRequest) -> dict:
        """批量选股筛选。"""
        try:
            return run_stock_screening(
                pool_date=req.pool_date,
                start_date=req.start_date,
                end_date=req.end_date,
                signal=req.signal,
                signal_params=req.signal_params,
                top_n=req.top_n,
                cash=req.cash,
                symbols=req.symbols,
            )
        except (ValueError, DataLoadError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


def run_api_server(*, host: str, port: int) -> None:
    """启动 FastAPI 服务。"""

    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError(WEB_DEPENDENCY_HINT) from exc

    app = create_api_app()
    print(f"QuantBalance API is ready to start: http://{host}:{port}")
    print(f"接口文档地址：http://{host}:{port}/docs")
    uvicorn.run(app, host=host, port=port)
