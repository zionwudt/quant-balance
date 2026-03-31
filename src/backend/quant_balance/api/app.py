"""FastAPI 应用工厂 — 组装路由、中间件与生命周期事件。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from quant_balance import __version__
from quant_balance.infra.logging import get_logger
from quant_balance.paths import WEB_DIR

WEB_DEPENDENCY_HINT = "启动 API 模式需要先安装项目依赖：pip install -e ."

logger = get_logger(__name__)

# ── 模块级单例，供路由模块通过 lazy import 访问 ──
_scheduler_manager = None
_paper_manager = None


def _get_scheduler_manager():
    """返回全局 DailyScanScheduler 单例（由 create_api_app 初始化）。"""
    return _scheduler_manager


def _get_paper_manager():
    """返回全局 PaperTradingManager 单例（由 create_api_app 初始化）。"""
    return _paper_manager


def create_api_app() -> Any:
    """创建并返回 FastAPI 应用实例。"""
    global _scheduler_manager, _paper_manager  # noqa: PLW0603

    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError(WEB_DEPENDENCY_HINT) from exc

    from quant_balance.execution.paper_trading import PaperTradingManager
    from quant_balance.infra.scheduler import DailyScanScheduler
    from quant_balance.api.routes import all_routers

    # ── 全局单例管理器 ──
    _scheduler_manager = DailyScanScheduler()
    _paper_manager = PaperTradingManager()

    @asynccontextmanager
    async def lifespan(app: Any) -> AsyncIterator[None]:
        app.state.scheduler_manager = _scheduler_manager
        app.state.paper_manager = _paper_manager
        _scheduler_manager.start()
        yield
        _scheduler_manager.shutdown()

    app = FastAPI(
        title="QuantBalance API",
        version=__version__,
        description="QuantBalance 回测与研究接口 — backtesting.py + vectorbt",
        lifespan=lifespan,
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

    @app.get("/favicon.svg")
    def favicon():
        """返回 Web 前端 favicon。"""
        favicon_path = WEB_DIR / "favicon.svg"
        if favicon_path.is_file():
            return FileResponse(str(favicon_path), media_type="image/svg+xml")
        raise HTTPException(status_code=404, detail="favicon not found")

    # ── 注册路由模块 ──
    for router in all_routers:
        app.include_router(router)

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
