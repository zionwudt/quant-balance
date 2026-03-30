"""API 路由模块。"""

from quant_balance.api.routes.backtest import router as backtest_router
from quant_balance.api.routes.paper import router as paper_router
from quant_balance.api.routes.screening import router as screening_router
from quant_balance.api.routes.signals import router as signals_router
from quant_balance.api.routes.system import router as system_router

all_routers = [
    system_router,
    backtest_router,
    screening_router,
    signals_router,
    paper_router,
]

__all__ = [
    "all_routers",
    "backtest_router",
    "paper_router",
    "screening_router",
    "signals_router",
    "system_router",
]

