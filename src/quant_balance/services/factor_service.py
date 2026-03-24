"""多因子服务 —— 编排历史股票池与财务快照。"""

from __future__ import annotations

from dataclasses import asdict
from time import perf_counter

from quant_balance.core.factors import DEFAULT_FACTOR_SPECS, rank_factor_items, resolve_factor_specs
from quant_balance.data.fundamental_loader import load_financial_at
from quant_balance.data.stock_pool import filter_pool_at_date
from quant_balance.logging_utils import get_logger, log_event

logger = get_logger(__name__)


def run_factor_ranking(
    *,
    pool_date: str,
    factors: list[dict] | None = None,
    top_n: int = 50,
    symbols: list[str] | None = None,
    pool_filters: dict | None = None,
) -> dict[str, object]:
    """执行多因子打分与排名。"""

    if top_n <= 0:
        raise ValueError("top_n 必须 > 0")

    started_at = perf_counter()
    factor_specs = resolve_factor_specs(factors or list(DEFAULT_FACTOR_SPECS))
    records = filter_pool_at_date(
        pool_date,
        filters=pool_filters if _has_active_pool_filters(pool_filters) else None,
        symbols=symbols,
    )

    candidate_rows: list[dict[str, object]] = []
    metadata_by_symbol: dict[str, dict[str, object]] = {}
    missing_financial_symbols: list[str] = []
    for record in records:
        snapshot = load_financial_at(record.ts_code, pool_date)
        if snapshot is None:
            missing_financial_symbols.append(record.ts_code)
            continue

        record_payload = asdict(record)
        snapshot_payload = asdict(snapshot)
        symbol = record.ts_code
        metadata_by_symbol[symbol] = {
            "symbol": symbol,
            "name": record.name,
            "industry": record.industry,
            "market": record.market,
            "listing_days": record.listing_days,
            "ann_date": snapshot.ann_date,
            "end_date": snapshot.end_date,
        }
        candidate_rows.append({
            "symbol": symbol,
            **record_payload,
            **snapshot_payload,
        })

    result = rank_factor_items(candidate_rows, factor_specs)
    ranked = result.rankings.head(top_n)
    ordered_symbols = ranked.index.tolist()
    rankings = []
    for symbol, row in ranked.iterrows():
        rankings.append(
            {
                **metadata_by_symbol.get(symbol, {"symbol": symbol}),
                "total_score": float(row["total_score"]),
                "rank": int(row["rank"]),
                "factors": {
                    spec.name: {
                        "raw_value": _jsonable_factor_value(result.raw_values.at[symbol, spec.name]),
                        "score": _jsonable_factor_value(result.scores.at[symbol, spec.name]),
                        "weight": float(result.normalized_weights[spec.name]),
                        "direction": result.factor_directions[spec.name],
                    }
                    for spec in factor_specs
                },
            }
        )

    payload = {
        "symbols": ordered_symbols,
        "weights": {
            spec.name: float(result.normalized_weights[spec.name])
            for spec in factor_specs
        },
        "rankings": rankings,
        "run_context": {
            "pool_date": pool_date,
            "pool_filters": pool_filters or {},
            "requested_symbols_count": len(symbols) if symbols is not None else None,
            "candidate_count": len(records),
            "scored_count": len(result.rankings),
            "top_n": top_n,
            "skipped_symbols_no_financial": missing_financial_symbols,
            "skipped_symbols_missing_factors": result.skipped_symbols,
            "factors": [
                {
                    "name": spec.name,
                    "weight": float(result.normalized_weights[spec.name]),
                    "direction": result.factor_directions[spec.name],
                }
                for spec in factor_specs
            ],
        },
    }
    log_event(
        logger,
        "FACTORS_RANK",
        pool_date=pool_date,
        pool_filters=pool_filters or {},
        requested_symbols_count=len(symbols) if symbols is not None else None,
        candidate_count=len(records),
        scored_count=len(result.rankings),
        top_n=top_n,
        factors=payload["run_context"]["factors"],
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
    )
    return payload


def _jsonable_factor_value(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _has_active_pool_filters(pool_filters: dict | None) -> bool:
    if not pool_filters:
        return False
    return any(value not in (None, False, [], {}, "") for value in pool_filters.values())
