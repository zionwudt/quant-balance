"""系统级路由 — 健康检查、元信息、配置、调度器、策略列表、搜索、市场状态、通知。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from quant_balance.api.deps import log_api_error
from quant_balance.api.schemas import (
    NotifyTestRequest,
    SchedulerRunRequest,
    TushareTokenRequest,
)
from quant_balance.core.strategies import SIGNAL_REGISTRY, STRATEGY_REGISTRY
from quant_balance.data import DataLoadError

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/meta")
def api_meta() -> dict[str, object]:
    """返回前端初始化所需的元信息。"""
    from quant_balance.api.meta import build_api_meta

    return build_api_meta()


@router.get("/api/config/status")
def config_status() -> dict[str, object]:
    """返回首次使用配置状态。"""
    from quant_balance.data.common import get_tushare_config_status

    return get_tushare_config_status(check_connection=True)


@router.post("/api/config/tushare-token")
def save_tushare_config(req: TushareTokenRequest) -> dict[str, object]:
    """验证并保存 Tushare token。"""
    from quant_balance.data.common import (
        get_tushare_config_status,
        save_tushare_token,
        validate_tushare_token,
    )

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
        log_api_error(
            endpoint="/api/config/tushare-token",
            status_code=400,
            exc=exc,
            context=context,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(
            endpoint="/api/config/tushare-token",
            status_code=500,
            exc=exc,
            context=context,
        )
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.get("/api/scheduler/status")
def scheduler_status() -> dict[str, object]:
    """返回定时调度器状态。"""
    from quant_balance.api.app import _get_scheduler_manager

    return _get_scheduler_manager().get_status()


@router.post("/api/scheduler/run")
def scheduler_run(req: SchedulerRunRequest) -> dict[str, object]:
    """手动触发一次盘后扫描。"""
    from quant_balance.api.app import _get_scheduler_manager

    context = {
        "trade_date": req.trade_date,
        "force": req.force,
    }
    try:
        return _get_scheduler_manager().run_manual_scan(
            trade_date=req.trade_date,
            force=req.force,
        )
    except (ValueError, DataLoadError) as exc:
        log_api_error(
            endpoint="/api/scheduler/run",
            status_code=400,
            exc=exc,
            context=context,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(
            endpoint="/api/scheduler/run",
            status_code=500,
            exc=exc,
            context=context,
        )
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.get("/api/strategies")
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


@router.get("/api/symbols/search")
def symbols_search(q: str, limit: int = 8) -> dict[str, object]:
    """按代码或名称搜索股票/基准指数候选。"""
    from quant_balance.services.symbol_search_service import search_symbol_candidates

    context = {"query": q, "limit": limit}
    try:
        return {
            "query": q,
            "items": search_symbol_candidates(q, limit=limit),
        }
    except (ValueError, DataLoadError) as exc:
        log_api_error(
            endpoint="/api/symbols/search",
            status_code=400,
            exc=exc,
            context=context,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(
            endpoint="/api/symbols/search",
            status_code=500,
            exc=exc,
            context=context,
        )
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.get("/api/market/regime")
def market_regime(
    symbol: str = "000300.SH",
    start_date: str | None = None,
    end_date: str | None = None,
    data_provider: str | None = None,
) -> dict[str, object]:
    """返回当前市场状态或区间状态序列。"""
    from quant_balance.services.regime_service import run_market_regime_analysis

    context = {
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
        "data_provider": data_provider,
    }
    try:
        kwargs: dict = {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
        }
        if data_provider is not None:
            kwargs["data_provider"] = data_provider
        return run_market_regime_analysis(**kwargs)
    except (ValueError, DataLoadError) as exc:
        log_api_error(
            endpoint="/api/market/regime",
            status_code=400,
            exc=exc,
            context=context,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(
            endpoint="/api/market/regime",
            status_code=500,
            exc=exc,
            context=context,
        )
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.post("/api/notify/test")
def notify_test(req: NotifyTestRequest) -> dict[str, object]:
    """测试通知渠道连通性。"""
    from quant_balance.notify import send_configured_notifications

    context = {"enabled": list(req.enabled)}
    try:
        items = send_configured_notifications(
            title=req.title,
            content=req.content,
            config=req.to_notify_config(),
        )
        return {
            "items": items,
            "success_count": sum(1 for item in items if item.get("status") == "sent"),
            "failure_count": sum(1 for item in items if item.get("status") != "sent"),
        }
    except ValueError as exc:
        log_api_error(
            endpoint="/api/notify/test",
            status_code=400,
            exc=exc,
            context=context,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(
            endpoint="/api/notify/test",
            status_code=500,
            exc=exc,
            context=context,
        )
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc

