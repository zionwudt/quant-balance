"""FastAPI 应用 — 回测与筛选接口。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from quant_balance import __version__
from quant_balance.api.schemas import (
    BacktestRunRequest,
    OptimizeRequest,
    PortfolioRunRequest,
    ScreeningRunRequest,
    StockPoolFilterRequest,
    TushareTokenRequest,
)
from quant_balance.core.strategies import SIGNAL_REGISTRY, STRATEGY_REGISTRY
from quant_balance.logging_utils import get_logger, log_event

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

WEB_DEPENDENCY_HINT = "启动 API 模式需要先安装项目依赖：pip install -e ."

logger = get_logger(__name__)


def _log_api_error(
    *,
    endpoint: str,
    status_code: int,
    exc: Exception,
    context: dict[str, object],
) -> None:
    log_event(
        logger,
        "API_ERROR",
        level=logging.WARNING if status_code < 500 else logging.ERROR,
        exc_info=status_code >= 500,
        endpoint=endpoint,
        status_code=status_code,
        error_type=type(exc).__name__,
        detail=str(exc),
        **context,
    )


def create_api_app() -> Any:
    """创建 FastAPI 应用。"""

    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError(WEB_DEPENDENCY_HINT) from exc

    from quant_balance.api.meta import build_api_meta
    from quant_balance.data import DataLoadError
    from quant_balance.data.common import (
        get_tushare_config_status,
        save_tushare_token,
        validate_tushare_token,
    )
    from quant_balance.services.backtest_service import run_optimize, run_single_backtest
    from quant_balance.services.portfolio_service import run_portfolio_research
    from quant_balance.services.screening_service import run_stock_screening
    from quant_balance.services.stock_pool_service import run_stock_pool_filter

    app = FastAPI(
        title="QuantBalance API",
        version=__version__,
        description="QuantBalance 回测与研究接口 — backtesting.py + vectorbt",
    )

    # ── Web 前端静态文件 ──
    static_dir = WEB_DIR / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    def dashboard():
        """返回 Web 前端入口页面。"""
        index_path = WEB_DIR / "index.html"
        if index_path.is_file():
            return FileResponse(str(index_path))
        return {"message": "QuantBalance API is running. Visit /docs for API documentation."}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/meta")
    def api_meta() -> dict[str, object]:
        """返回前端初始化所需的元信息。"""
        return build_api_meta()

    @app.get("/api/config/status")
    def config_status() -> dict[str, object]:
        """返回首次使用配置状态。"""

        return get_tushare_config_status(check_connection=True)

    @app.post("/api/config/tushare-token")
    def save_tushare_config(req: TushareTokenRequest) -> dict[str, object]:
        """验证并保存 Tushare token。"""

        context = {"validate_only": req.validate_only}
        try:
            connection_ok, message = validate_tushare_token(req.token)
            if not connection_ok:
                raise ValueError(message)

            if not req.validate_only:
                save_tushare_token(req.token)

            status = get_tushare_config_status(check_connection=False)
            status["connection_checked"] = True
            status["connection_ok"] = True
            status["saved"] = not req.validate_only
            status["validate_only"] = req.validate_only
            status["message"] = (
                "Tushare token 验证成功。"
                if req.validate_only
                else "Tushare token 已保存。"
            )
            return status
        except ValueError as exc:
            _log_api_error(
                endpoint="/api/config/tushare-token",
                status_code=400,
                exc=exc,
                context=context,
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            _log_api_error(
                endpoint="/api/config/tushare-token",
                status_code=500,
                exc=exc,
                context=context,
            )
            raise HTTPException(status_code=500, detail="内部服务器错误") from exc

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

    @app.post("/api/stock-pool/filter")
    def stock_pool_filter(req: StockPoolFilterRequest) -> dict:
        """历史股票池过滤。"""
        filters = req.filters.model_dump(exclude_none=True, exclude_defaults=True)
        context = {
            "pool_date": req.pool_date,
            "filters": filters,
            "symbols_count": len(req.symbols) if req.symbols is not None else None,
        }
        try:
            return run_stock_pool_filter(
                pool_date=req.pool_date,
                filters=filters,
                symbols=req.symbols,
            )
        except (ValueError, DataLoadError) as exc:
            _log_api_error(
                endpoint="/api/stock-pool/filter",
                status_code=400,
                exc=exc,
                context=context,
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            _log_api_error(
                endpoint="/api/stock-pool/filter",
                status_code=500,
                exc=exc,
                context=context,
            )
            raise HTTPException(status_code=500, detail="内部服务器错误") from exc

    @app.post("/api/backtest/run")
    def backtest_run(req: BacktestRunRequest) -> dict:
        """单股精细回测。"""
        context = {
            "symbol": req.symbol,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "strategy": req.strategy,
            "cash": req.cash,
            "commission": req.commission,
            "data_provider": req.data_provider,
        }
        try:
            kwargs = {
                "symbol": req.symbol,
                "start_date": req.start_date,
                "end_date": req.end_date,
                "strategy": req.strategy,
                "cash": req.cash,
                "commission": req.commission,
                "params": req.params,
            }
            if req.data_provider is not None:
                kwargs["data_provider"] = req.data_provider
            return run_single_backtest(**kwargs)
        except (ValueError, DataLoadError) as exc:
            _log_api_error(
                endpoint="/api/backtest/run",
                status_code=400,
                exc=exc,
                context=context,
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            _log_api_error(
                endpoint="/api/backtest/run",
                status_code=500,
                exc=exc,
                context=context,
            )
            raise HTTPException(status_code=500, detail="内部服务器错误") from exc

    @app.post("/api/backtest/optimize")
    def backtest_optimize(req: OptimizeRequest) -> dict:
        """参数优化。"""
        context = {
            "symbol": req.symbol,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "strategy": req.strategy,
            "cash": req.cash,
            "commission": req.commission,
            "maximize": req.maximize,
            "data_provider": req.data_provider,
        }
        try:
            kwargs = {
                "symbol": req.symbol,
                "start_date": req.start_date,
                "end_date": req.end_date,
                "strategy": req.strategy,
                "cash": req.cash,
                "commission": req.commission,
                "maximize": req.maximize,
                "param_ranges": req.param_ranges,
            }
            if req.data_provider is not None:
                kwargs["data_provider"] = req.data_provider
            return run_optimize(**kwargs)
        except (ValueError, DataLoadError) as exc:
            _log_api_error(
                endpoint="/api/backtest/optimize",
                status_code=400,
                exc=exc,
                context=context,
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            _log_api_error(
                endpoint="/api/backtest/optimize",
                status_code=500,
                exc=exc,
                context=context,
            )
            raise HTTPException(status_code=500, detail="内部服务器错误") from exc

    @app.post("/api/screening/run")
    def screening_run(req: ScreeningRunRequest) -> dict:
        """批量选股筛选。"""
        context = {
            "pool_date": req.pool_date,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "signal": req.signal,
            "pool_filters": req.pool_filters.model_dump(exclude_none=True, exclude_defaults=True),
            "top_n": req.top_n,
            "cash": req.cash,
            "symbols_count": len(req.symbols) if req.symbols is not None else None,
            "data_provider": req.data_provider,
        }
        try:
            kwargs = {
                "pool_date": req.pool_date,
                "start_date": req.start_date,
                "end_date": req.end_date,
                "signal": req.signal,
                "signal_params": req.signal_params,
                "pool_filters": req.pool_filters.model_dump(exclude_none=True, exclude_defaults=True),
                "top_n": req.top_n,
                "cash": req.cash,
                "symbols": req.symbols,
            }
            if req.data_provider is not None:
                kwargs["data_provider"] = req.data_provider
            return run_stock_screening(**kwargs)
        except (ValueError, DataLoadError) as exc:
            _log_api_error(
                endpoint="/api/screening/run",
                status_code=400,
                exc=exc,
                context=context,
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            _log_api_error(
                endpoint="/api/screening/run",
                status_code=500,
                exc=exc,
                context=context,
            )
            raise HTTPException(status_code=500, detail="内部服务器错误") from exc

    @app.post("/api/portfolio/run")
    def portfolio_run(req: PortfolioRunRequest) -> dict:
        """组合回测。"""
        context = {
            "symbols_count": len(req.symbols),
            "start_date": req.start_date,
            "end_date": req.end_date,
            "allocation": req.allocation,
            "rebalance_frequency": req.rebalance_frequency,
            "cash": req.cash,
            "commission": req.commission,
            "data_provider": req.data_provider,
        }
        try:
            kwargs = {
                "symbols": req.symbols,
                "start_date": req.start_date,
                "end_date": req.end_date,
                "allocation": req.allocation,
                "weights": req.weights,
                "rebalance_frequency": req.rebalance_frequency,
                "cash": req.cash,
                "commission": req.commission,
            }
            if req.data_provider is not None:
                kwargs["data_provider"] = req.data_provider
            return run_portfolio_research(**kwargs)
        except (ValueError, DataLoadError) as exc:
            _log_api_error(
                endpoint="/api/portfolio/run",
                status_code=400,
                exc=exc,
                context=context,
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            _log_api_error(
                endpoint="/api/portfolio/run",
                status_code=500,
                exc=exc,
                context=context,
            )
            raise HTTPException(status_code=500, detail="内部服务器错误") from exc

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
