"""筛选路由 — 批量选股、股票池过滤、多因子排名、组合回测。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from quant_balance.api.deps import log_api_error
from quant_balance.api.schemas import (
    FactorsRankRequest,
    PortfolioRunRequest,
    ScreeningRunRequest,
    StockPoolFilterRequest,
)
from quant_balance.data import DataLoadError

router = APIRouter(tags=["screening"])


@router.post("/api/screening/run")
def screening_run(req: ScreeningRunRequest) -> dict:
    """批量选股筛选。"""
    from quant_balance.services.screening_service import run_stock_screening

    context = {
        "pool_date": req.pool_date,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "asset_type": req.asset_type,
        "timeframe": req.timeframe,
        "signal": req.signal,
        "pool_filters": req.pool_filters.model_dump(exclude_none=True, exclude_defaults=True),
        "market_regime": req.market_regime,
        "market_regime_symbol": req.market_regime_symbol,
        "top_n": req.top_n,
        "cash": req.cash,
        "symbols_count": len(req.symbols) if req.symbols is not None else None,
        "data_provider": req.data_provider,
    }
    try:
        kwargs: dict = {
            "pool_date": req.pool_date,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "asset_type": req.asset_type,
            "timeframe": req.timeframe,
            "signal": req.signal,
            "signal_params": req.signal_params,
            "pool_filters": req.pool_filters.model_dump(exclude_none=True, exclude_defaults=True),
            "market_regime": req.market_regime,
            "market_regime_symbol": req.market_regime_symbol,
            "top_n": req.top_n,
            "cash": req.cash,
            "symbols": req.symbols,
        }
        if req.data_provider is not None:
            kwargs["data_provider"] = req.data_provider
        return run_stock_screening(**kwargs)
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/screening/run", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/screening/run", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.post("/api/stock-pool/filter")
def stock_pool_filter(req: StockPoolFilterRequest) -> dict:
    """历史股票池过滤。"""
    from quant_balance.services.stock_pool_service import run_stock_pool_filter

    filters = req.filters.model_dump(exclude_none=True, exclude_defaults=True)
    context = {
        "pool_date": req.pool_date,
        "filters": filters,
        "symbols_count": len(req.symbols) if req.symbols is not None else None,
        "data_provider": req.data_provider,
    }
    try:
        kwargs: dict = {
            "pool_date": req.pool_date,
            "filters": filters,
            "symbols": req.symbols,
        }
        if req.data_provider is not None:
            kwargs["data_provider"] = req.data_provider
        return run_stock_pool_filter(**kwargs)
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/stock-pool/filter", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/stock-pool/filter", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.post("/api/factors/rank")
def factors_rank(req: FactorsRankRequest) -> dict:
    """多因子打分与排名。"""
    from quant_balance.services.factor_service import run_factor_ranking

    factors = [
        factor.model_dump(exclude_none=True)
        for factor in req.factors
    ]
    pool_filters = req.pool_filters.model_dump(exclude_none=True, exclude_defaults=True)
    context = {
        "pool_date": req.pool_date,
        "factors": factors,
        "pool_filters": pool_filters,
        "market_regime": req.market_regime,
        "market_regime_symbol": req.market_regime_symbol,
        "top_n": req.top_n,
        "symbols_count": len(req.symbols) if req.symbols is not None else None,
        "data_provider": req.data_provider,
    }
    try:
        kwargs: dict = {
            "pool_date": req.pool_date,
            "factors": factors,
            "pool_filters": pool_filters,
            "market_regime": req.market_regime,
            "market_regime_symbol": req.market_regime_symbol,
            "top_n": req.top_n,
            "symbols": req.symbols,
        }
        if req.data_provider is not None:
            kwargs["data_provider"] = req.data_provider
        return run_factor_ranking(**kwargs)
    except (ValueError, DataLoadError) as exc:
        log_api_error(endpoint="/api/factors/rank", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/factors/rank", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc


@router.post("/api/portfolio/run")
def portfolio_run(req: PortfolioRunRequest) -> dict:
    """组合回测。"""
    from quant_balance.services.portfolio_service import run_portfolio_research

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
        kwargs: dict = {
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
        log_api_error(endpoint="/api/portfolio/run", status_code=400, exc=exc, context=context)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log_api_error(endpoint="/api/portfolio/run", status_code=500, exc=exc, context=context)
        raise HTTPException(status_code=500, detail="内部服务器错误") from exc

