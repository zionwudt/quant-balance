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
        # 启动前校验调度器配置，快速失败
        _validate_scheduler_config()
        _scheduler_manager.start()
        # 后台预加载 vectorbt，减少首次请求延迟
        import threading
        threading.Thread(target=_preload_vectorbt, daemon=True).start()
        yield
        _scheduler_manager.shutdown()

    app = FastAPI(
        title="QuantBalance API",
        version=__version__,
        description="QuantBalance 回测与研究接口 — backtesting.py + vectorbt",
        lifespan=lifespan,
    )

    # ── API Key 认证中间件 ──
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse
    from quant_balance.api.deps import load_api_key, verify_api_key

    _api_key = load_api_key()

    class ApiKeyMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            auth = request.headers.get("Authorization") or request.headers.get("X-API-Key")
            if not verify_api_key(request.url.path, auth, _api_key):
                return JSONResponse({"detail": "未授权，请提供有效的 API Key。"}, status_code=401)
            return await call_next(request)

    if _api_key:
        app.add_middleware(ApiKeyMiddleware)

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


def _preload_vectorbt() -> None:
    """后台线程预加载 vectorbt，避免首次请求 2-3 秒延迟。"""
    try:
        import vectorbt  # noqa: F401
        logger.info("vectorbt 预加载完成")
    except ImportError:
        pass


def _validate_scheduler_config() -> None:
    """启动时校验调度器配置，配置错误立即报告。"""
    try:
        from quant_balance.infra.scheduler import load_scheduler_config
        load_scheduler_config()
        logger.info("调度器配置校验通过")
    except Exception as exc:
        logger.warning("调度器配置校验失败: %s", exc)
