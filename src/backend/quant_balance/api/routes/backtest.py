"""回测路由 — 单股回测、历史、对比、删除、参数优化。"""

from __future__ import annotations

import threading
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from quant_balance.api.deps import log_api_error
from quant_balance.api.schemas import BacktestRunRequest, OptimizeRequest
from quant_balance.data import DataLoadError

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

# ── 异步优化任务存储 ──
_optimize_tasks: dict[str, dict] = {}


@router.post("/run")
def backtest_run(req: BacktestRunRequest) -> dict:
    """单股精细回测。"""
    from quant_balance.data.result_store import save_backtest_run
    from quant_balance.services.backtest_service import run_single_backtest

    context = {
        "symbol": req.symbol,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "asset_type": req.asset_type,
        "timeframe": req.timeframe,
        "benchmark_symbol": req.benchmark_symbol,
        "benchmark_asset_type": req.benchmark_asset_type,
        "strategy": req.strategy,
        "cash": req.cash,
        "commission": req.commission,
        "slippage_mode": req.slippage_mode,
        "slippage_rate": req.slippage_rate,
        "data_provider": req.data_provider,
        "benchmark_data_provider": req.benchmark_data_provider,
    }
    try:
        kwargs: dict = {
            "symbol": req.symbol,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "asset_type": req.asset_type,
            "timeframe": req.timeframe,
            "strategy": req.strategy,
            "cash": req.cash,
            "commission": req.commission,
            "params": req.params,
        }
        if req.slippage_mode != "off":
            kwargs["slippage_mode"] = req.slippage_mode
        if req.slippage_rate > 0:
            kwargs["slippage_rate"] = req.slippage_rate
        if req.benchmark_symbol is not None:
            kwargs["benchmark_symbol"] = req.benchmark_symbol
        if req.benchmark_asset_type is not None:
            kwargs["benchmark_asset_type"] = req.benchmark_asset_type
        if req.data_provider is not None:
            kwargs["data_provider"] = req.data_provider
        if req.benchmark_data_provider is not None:
            kwargs["benchmark_data_provider"] = req.benchmark_data_provider
        result = run_single_backtest(**kwargs)
        save_backtest_run(
            request_payload=req.model_dump(exclude_none=True),
            result_payload=result,
        )
        return result
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/backtest/run", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/backtest/run", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.get("/history")
def backtest_history(
    page: int = 1,
    page_size: int = 20,
    symbol: str | None = None,
    strategy: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, object]:
    """分页查询单股回测历史。"""
    from quant_balance.data.result_store import list_backtest_runs

    context = {
        "page": page,
        "page_size": page_size,
        "symbol": symbol,
        "strategy": strategy,
        "date_from": date_from,
        "date_to": date_to,
    }
    try:
        return list_backtest_runs(
            page=page,
            page_size=page_size,
            symbol=symbol,
            strategy=strategy,
            date_from=date_from,
            date_to=date_to,
        )
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/backtest/history", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/backtest/history", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.get("/history/{run_id}")
def backtest_history_detail(run_id: str) -> dict[str, object]:
    """读取单条回测历史详情。"""
    from quant_balance.data.result_store import get_backtest_run

    context = {"run_id": run_id}
    try:
        return get_backtest_run(run_id)
    except LookupError as exc:
        log_api_error(endpoint="/api/backtest/history/{run_id}", status_code=404, exc=exc, context=context)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/backtest/history/{run_id}", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/backtest/history/{run_id}", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.get("/compare")
def backtest_compare(ids: str) -> dict[str, object]:
    """对比 2-3 条历史回测结果。"""
    from quant_balance.data.result_store import compare_backtest_runs

    normalized_ids = [item.strip() for item in str(ids or "").split(",") if item.strip()]
    context = {
        "ids": normalized_ids,
        "count": len(normalized_ids),
    }
    try:
        return compare_backtest_runs(normalized_ids)
    except LookupError as exc:
        log_api_error(endpoint="/api/backtest/compare", status_code=404, exc=exc, context=context)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/backtest/compare", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/backtest/compare", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.delete("/history/{run_id}")
def backtest_history_delete(run_id: str) -> dict[str, object]:
    """删除单条回测历史记录。"""
    from quant_balance.data.result_store import delete_backtest_run

    context = {"run_id": run_id}
    try:
        return delete_backtest_run(run_id)
    except LookupError as exc:
        log_api_error(endpoint="/api/backtest/history/{run_id}", status_code=404, exc=exc, context=context)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/backtest/history/{run_id}", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/backtest/history/{run_id}", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.post("/optimize")
def backtest_optimize(req: OptimizeRequest) -> dict:
    """参数优化。"""
    from quant_balance.services.backtest_service import run_optimize

    context = {
        "symbol": req.symbol,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "asset_type": req.asset_type,
        "strategy": req.strategy,
        "cash": req.cash,
        "commission": req.commission,
        "maximize": req.maximize,
        "top_n": req.top_n,
        "constraints_count": len(req.constraints),
        "walk_forward": req.walk_forward.model_dump(exclude_none=True) if req.walk_forward is not None else None,
        "data_provider": req.data_provider,
    }
    try:
        kwargs: dict = {
            "symbol": req.symbol,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "asset_type": req.asset_type,
            "strategy": req.strategy,
            "cash": req.cash,
            "commission": req.commission,
            "maximize": req.maximize,
            "param_ranges": req.param_ranges,
            "top_n": req.top_n,
            "constraints": [item.model_dump(exclude_none=True) for item in req.constraints],
        }
        if req.walk_forward is not None:
            kwargs["walk_forward"] = req.walk_forward.model_dump(exclude_none=True)
        if req.data_provider is not None:
            kwargs["data_provider"] = req.data_provider
        return run_optimize(**kwargs)
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/backtest/optimize", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/backtest/optimize", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.post("/optimize/async")
def backtest_optimize_async(req: OptimizeRequest) -> dict:
    """异步参数优化 — 立即返回 task_id，后台执行。"""
    from quant_balance.services.backtest_service import run_optimize

    task_id = uuid4().hex[:12]
    _optimize_tasks[task_id] = {"status": "running", "result": None, "error": None}

    kwargs: dict = {
        "symbol": req.symbol,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "asset_type": req.asset_type,
        "strategy": req.strategy,
        "cash": req.cash,
        "commission": req.commission,
        "maximize": req.maximize,
        "param_ranges": req.param_ranges,
        "top_n": req.top_n,
        "constraints": [item.model_dump(exclude_none=True) for item in req.constraints],
    }
    if req.walk_forward is not None:
        kwargs["walk_forward"] = req.walk_forward.model_dump(exclude_none=True)
    if req.data_provider is not None:
        kwargs["data_provider"] = req.data_provider

    def _run() -> None:
        try:
            result = run_optimize(**kwargs)
            _optimize_tasks[task_id] = {"status": "completed", "result": result, "error": None}
        except Exception as exc:  # noqa: BLE001
            _optimize_tasks[task_id] = {"status": "failed", "result": None, "error": str(exc)}

    threading.Thread(target=_run, daemon=True).start()
    return {"task_id": task_id, "status": "running"}


@router.get("/optimize/async/{task_id}")
def backtest_optimize_status(task_id: str) -> dict:
    """查询异步优化任务状态。"""
    task = _optimize_tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return {"task_id": task_id, **task}

