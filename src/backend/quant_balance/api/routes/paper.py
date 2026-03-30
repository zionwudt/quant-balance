"""模拟盘路由 — 启动、暂停、停止、状态查询。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from quant_balance.api.deps import log_api_error
from quant_balance.api.schemas import (
    PaperPauseRequest,
    PaperStartRequest,
    PaperStopRequest,
)
from quant_balance.data import DataLoadError

router = APIRouter(prefix="/api/paper", tags=["paper"])


@router.get("/status")
def paper_status(session_id: str | None = None, date: str | None = None) -> dict[str, object]:
    """返回模拟盘状态快照。"""
    from quant_balance.api.app import _get_paper_manager

    context = {"session_id": session_id, "date": date}
    try:
        return _get_paper_manager().get_status(session_id=session_id, as_of_date=date)
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/paper/status", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/paper/status", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.post("/start")
def paper_start(req: PaperStartRequest) -> dict[str, object]:
    """启动新的模拟盘会话。"""
    from quant_balance.api.app import _get_paper_manager

    context = {
        "strategy": req.strategy,
        "symbols_count": len(req.symbols),
        "asset_type": req.asset_type,
        "start_date": req.start_date,
    }
    try:
        return _get_paper_manager().start_session(
            strategy=req.strategy,
            strategy_params=req.strategy_params,
            symbols=req.symbols,
            initial_cash=req.initial_cash,
            asset_type=req.asset_type,
            start_date=req.start_date,
            data_provider=req.data_provider,
        )
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/paper/start", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/paper/start", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.post("/pause")
def paper_pause(req: PaperPauseRequest) -> dict[str, object]:
    """暂停当前模拟盘会话。"""
    from quant_balance.api.app import _get_paper_manager

    context = {"session_id": req.session_id}
    try:
        return _get_paper_manager().pause_session(session_id=req.session_id)
    except LookupError as exc:
        log_api_error(endpoint="/api/paper/pause", status_code=404, exc=exc, context=context)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/paper/pause", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/paper/pause", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.post("/stop")
def paper_stop(req: PaperStopRequest) -> dict[str, object]:
    """停止模拟盘并冻结最终报告。"""
    from quant_balance.api.app import _get_paper_manager

    context = {"session_id": req.session_id, "date": req.date}
    try:
        return _get_paper_manager().stop_session(session_id=req.session_id, as_of_date=req.date)
    except LookupError as exc:
        log_api_error(endpoint="/api/paper/stop", status_code=404, exc=exc, context=context)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/paper/stop", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/paper/stop", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc

