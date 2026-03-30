"""信号路由 — 信号查询、导出、状态更新。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from quant_balance.api.deps import log_api_error
from quant_balance.api.schemas import SignalStatusUpdateRequest
from quant_balance.data import DataLoadError

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("/recent")
def signals_recent(limit: int = 20, trade_date: str | None = None) -> dict[str, object]:
    """返回最近持久化的调度信号。"""
    from quant_balance.core.signals import list_recent_signals

    context = {"limit": limit, "trade_date": trade_date}
    try:
        return {
            "items": list_recent_signals(limit=limit, trade_date=trade_date),
        }
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/signals/recent", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/signals/recent", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.get("/today")
def signals_today(limit: int = 200, date: str | None = None) -> dict[str, object]:
    """返回当天生成的信号列表。"""
    from quant_balance.core.signals import list_today_signals

    context = {"limit": limit, "date": date}
    try:
        return list_today_signals(limit=limit, as_of_date=date)
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/signals/today", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/signals/today", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.get("/history")
def signals_history(days: int = 30, page: int = 1, page_size: int = 20) -> dict[str, object]:
    """按时间窗口查询历史信号。"""
    from quant_balance.core.signals import list_signal_history

    context = {"days": days, "page": page, "page_size": page_size}
    try:
        return list_signal_history(days=days, page=page, page_size=page_size)
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/signals/history", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/signals/history", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.get("/export")
def signals_export(format: str = "csv", date: str | None = None):
    """导出指定日期的信号文件。"""
    from quant_balance.execution.signal_export import export_signals_for_date

    context = {"format": format, "date": date}
    try:
        artifact = export_signals_for_date(format=format, date=date)
        return Response(
            content=artifact.content,
            media_type=artifact.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{artifact.filename}"',
                "X-Export-Format": artifact.format,
                "X-Export-Date": artifact.trade_date,
                "X-Export-Count": str(artifact.total),
            },
        )
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/signals/export", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/signals/export", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.patch("/{signal_id}")
def signal_update(signal_id: int, req: SignalStatusUpdateRequest) -> dict[str, object]:
    """更新单条信号的状态。"""
    from quant_balance.core.signals import update_signal_status

    context = {"signal_id": signal_id, "status": req.status}
    try:
        return update_signal_status(signal_id, status=req.status)
    except LookupError as exc:
        log_api_error(endpoint="/api/signals/{signal_id}", status_code=404, exc=exc, context=context)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/signals/{signal_id}", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/signals/{signal_id}", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc

