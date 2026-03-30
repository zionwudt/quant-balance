"""代码搜索服务。"""

from __future__ import annotations

from pathlib import Path

from quant_balance.data.stock_pool import search_stock_candidates

BENCHMARK_PRESETS: tuple[dict[str, str], ...] = (
    {"symbol": "000300.SH", "name": "沪深300", "asset_type": "stock", "market": "指数", "kind": "benchmark"},
    {"symbol": "000905.SH", "name": "中证500", "asset_type": "stock", "market": "指数", "kind": "benchmark"},
    {"symbol": "000852.SH", "name": "中证1000", "asset_type": "stock", "market": "指数", "kind": "benchmark"},
    {"symbol": "399006.SZ", "name": "创业板指", "asset_type": "stock", "market": "指数", "kind": "benchmark"},
    {"symbol": "000001.SH", "name": "上证指数", "asset_type": "stock", "market": "指数", "kind": "benchmark"},
)

BENCHMARK_INDEX_SYMBOLS = frozenset(item["symbol"] for item in BENCHMARK_PRESETS)


def search_symbol_candidates(
    query: str,
    *,
    limit: int = 8,
    db_path: Path | None = None,
) -> list[dict[str, str]]:
    """按代码/名称搜索股票与常见基准指数。"""

    normalized = str(query).strip()
    if not normalized or limit < 1:
        return []

    query_upper = normalized.upper()
    items: list[dict[str, str]] = []
    seen_symbols: set[str] = set()

    for preset in BENCHMARK_PRESETS:
        haystack = f"{preset['symbol']} {preset['name']}".upper()
        if query_upper not in haystack:
            continue
        items.append(dict(preset))
        seen_symbols.add(preset["symbol"])
        if len(items) >= limit:
            return items

    for item in search_stock_candidates(normalized, limit=limit * 2, db_path=db_path):
        symbol = item["symbol"]
        if symbol in seen_symbols:
            continue
        items.append({**item, "kind": "stock"})
        seen_symbols.add(symbol)
        if len(items) >= limit:
            break
    return items
