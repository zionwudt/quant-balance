"""组合收益归因：个股贡献、简化 Brinson 与成本拆解。

归因维度：
1. 个股贡献: 每只股票对组合的收益贡献
2. 行业配置效应: 超配/低配行业带来的收益差异
3. 行业选股效应: 行业内选股的超额收益
4. 成本拆解: 手续费、印花税、滑点分析

Brinson 模型简化说明：
基准 = 同股票池首日等权买入并持有
组合 vs 基准的差异分解为配置效应、选股效应和交互效应
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

DEFAULT_BENCHMARK_LABEL = "同股票池等权买入持有"
_BUY_SIDE = 0
_SELL_SIDE = 1


@dataclass(slots=True)
class StockContribution:
    """单只股票的收益贡献。"""

    symbol: str
    name: str
    sector: str
    pnl: float
    contribution_pct: float
    contribution_share_pct: float
    buy_notional: float
    sell_notional: float
    final_value: float
    fees: float
    final_weight_pct: float


@dataclass(slots=True)
class SectorAttribution:
    """行业层面的单项 Brinson 归因。"""

    sector: str
    effect_pct: float
    active_contribution_pct: float
    portfolio_weight_pct: float
    benchmark_weight_pct: float
    portfolio_return_pct: float
    benchmark_return_pct: float
    portfolio_contribution_pct: float
    benchmark_contribution_pct: float


@dataclass(slots=True)
class SectorAttributionSummary:
    """行业层面的完整 Brinson 拆解。"""

    sector: str
    portfolio_weight_pct: float
    benchmark_weight_pct: float
    portfolio_return_pct: float
    benchmark_return_pct: float
    portfolio_contribution_pct: float
    benchmark_contribution_pct: float
    active_contribution_pct: float
    allocation_effect_pct: float
    selection_effect_pct: float
    interaction_effect_pct: float


@dataclass(slots=True)
class CostBreakdown:
    """交易成本拆解。"""

    commission: float
    stamp_tax: float
    slippage: float
    total_cost: float
    commission_share_pct: float
    stamp_tax_share_pct: float
    slippage_share_pct: float
    cost_rate_pct: float
    traded_notional: float
    turnover_pct: float
    cost_to_turnover_bps: float
    buy_notional: float
    sell_notional: float
    orders_count: int


@dataclass(slots=True)
class AttributionBenchmark:
    """归因基准摘要。"""

    label: str
    methodology: str
    portfolio_total_return_pct: float
    benchmark_total_return_pct: float
    excess_return_pct: float


@dataclass(slots=True)
class AttributionReport:
    """组合收益归因报告。"""

    stock_contributions: list[StockContribution]
    sector_allocation: list[SectorAttribution]
    sector_selection: list[SectorAttribution]
    sector_interaction: list[SectorAttribution]
    sector_summary: list[SectorAttributionSummary]
    cost_breakdown: CostBreakdown
    benchmark: AttributionBenchmark

    def to_dict(self) -> dict[str, object]:
        """转成 JSON 友好的字典。"""

        return asdict(self)


def build_portfolio_attribution(
    *,
    close_matrix: pd.DataFrame,
    portfolio,
    benchmark,
    initial_cash: float,
    symbol_metadata: dict[str, dict[str, str]] | None = None,
    benchmark_label: str = DEFAULT_BENCHMARK_LABEL,
) -> AttributionReport:
    """基于组合账本构建归因报告。"""

    if close_matrix.empty:
        raise ValueError("close_matrix 不能为空")

    final_prices = close_matrix.iloc[-1]
    metadata = _normalize_symbol_metadata(close_matrix.columns, symbol_metadata)
    portfolio_orders = _extract_orders(portfolio, close_matrix.columns)
    benchmark_orders = _extract_orders(benchmark, close_matrix.columns)

    portfolio_stocks = _build_stock_contributions(
        orders=portfolio_orders,
        asset_units=_final_asset_units(portfolio),
        final_prices=final_prices,
        initial_cash=initial_cash,
        metadata=metadata,
    )
    benchmark_stocks = _build_stock_contributions(
        orders=benchmark_orders,
        asset_units=_final_asset_units(benchmark),
        final_prices=final_prices,
        initial_cash=initial_cash,
        metadata=metadata,
    )

    portfolio_sector_contrib = _group_contribution_by_sector(portfolio_stocks)
    benchmark_sector_contrib = _group_contribution_by_sector(benchmark_stocks)
    portfolio_sector_weights = _average_sector_weights(
        _build_realized_weights(portfolio),
        metadata,
    )
    benchmark_sector_weights = _average_sector_weights(
        _build_realized_weights(benchmark),
        metadata,
    )

    sector_summary = _build_sector_summary(
        portfolio_sector_contrib=portfolio_sector_contrib,
        benchmark_sector_contrib=benchmark_sector_contrib,
        portfolio_sector_weights=portfolio_sector_weights,
        benchmark_sector_weights=benchmark_sector_weights,
    )
    cost_breakdown = _build_cost_breakdown(
        orders=portfolio_orders,
        initial_cash=initial_cash,
    )

    portfolio_total_return_pct = sum(item.contribution_pct for item in portfolio_stocks)
    benchmark_total_return_pct = sum(item.contribution_pct for item in benchmark_stocks)
    excess_return_pct = portfolio_total_return_pct - benchmark_total_return_pct

    return AttributionReport(
        stock_contributions=portfolio_stocks,
        sector_allocation=[
            _summary_to_sector_effect(item, effect_pct=item.allocation_effect_pct)
            for item in sector_summary
        ],
        sector_selection=[
            _summary_to_sector_effect(item, effect_pct=item.selection_effect_pct)
            for item in sector_summary
        ],
        sector_interaction=[
            _summary_to_sector_effect(item, effect_pct=item.interaction_effect_pct)
            for item in sector_summary
        ],
        sector_summary=sector_summary,
        cost_breakdown=cost_breakdown,
        benchmark=AttributionBenchmark(
            label=benchmark_label,
            methodology="以同一股票池首日等权买入并持有作为简化 Brinson 对照基准。",
            portfolio_total_return_pct=_round(portfolio_total_return_pct),
            benchmark_total_return_pct=_round(benchmark_total_return_pct),
            excess_return_pct=_round(excess_return_pct),
        ),
    )


def _normalize_symbol_metadata(
    symbols: pd.Index,
    symbol_metadata: dict[str, dict[str, str]] | None,
) -> dict[str, dict[str, str]]:
    metadata = symbol_metadata or {}
    normalized: dict[str, dict[str, str]] = {}
    for symbol in symbols:
        entry = metadata.get(str(symbol), {})
        normalized[str(symbol)] = {
            "name": str(entry.get("name", "") or symbol),
            "sector": str(
                entry.get("industry", "") or entry.get("sector", "") or "未分类"
            ),
        }
    return normalized


def _extract_orders(portfolio, symbols: pd.Index) -> pd.DataFrame:
    records = pd.DataFrame(portfolio.orders.records.copy())
    if records.empty:
        return pd.DataFrame(
            columns=["symbol", "side", "size", "price", "fees", "notional"]
        )

    symbol_map = {index: str(symbol) for index, symbol in enumerate(symbols)}
    records["symbol"] = records["col"].astype(int).map(symbol_map)
    records["side"] = records["side"].astype(int)
    records["size"] = records["size"].astype(float)
    records["price"] = records["price"].astype(float)
    records["fees"] = records["fees"].astype(float)
    records["notional"] = records["size"] * records["price"]
    return records[["symbol", "side", "size", "price", "fees", "notional"]]


def _final_asset_units(portfolio) -> pd.Series:
    assets = portfolio.assets()
    if isinstance(assets, pd.Series):
        return assets.astype(float)
    if assets is None or assets.empty:
        return pd.Series(dtype=float)
    return assets.iloc[-1].astype(float)


def _build_stock_contributions(
    *,
    orders: pd.DataFrame,
    asset_units: pd.Series,
    final_prices: pd.Series,
    initial_cash: float,
    metadata: dict[str, dict[str, str]],
) -> list[StockContribution]:
    records: list[StockContribution] = []
    total_final_value = float(
        (asset_units.reindex(final_prices.index).fillna(0.0) * final_prices).sum()
    )

    for symbol in final_prices.index:
        symbol_orders = orders[orders["symbol"] == symbol]
        buys = symbol_orders[symbol_orders["side"] == _BUY_SIDE]
        sells = symbol_orders[symbol_orders["side"] == _SELL_SIDE]
        buy_notional = float(buys["notional"].sum())
        sell_notional = float(sells["notional"].sum())
        fees = float(symbol_orders["fees"].sum())
        final_value = float(asset_units.get(symbol, 0.0) * final_prices[symbol])
        pnl = float((buy_notional * -1) + sell_notional + final_value - fees)
        records.append(
            StockContribution(
                symbol=str(symbol),
                name=metadata[str(symbol)]["name"],
                sector=metadata[str(symbol)]["sector"],
                pnl=_round(pnl),
                contribution_pct=_round(pnl / initial_cash * 100),
                contribution_share_pct=0.0,
                buy_notional=_round_money(buy_notional),
                sell_notional=_round_money(sell_notional),
                final_value=_round_money(final_value),
                fees=_round_money(fees),
                final_weight_pct=_round(
                    final_value / total_final_value * 100
                    if total_final_value > 0
                    else 0.0
                ),
            )
        )

    total_pnl = sum(item.pnl for item in records)
    normalized: list[StockContribution] = []
    for item in records:
        normalized.append(
            StockContribution(
                symbol=item.symbol,
                name=item.name,
                sector=item.sector,
                pnl=item.pnl,
                contribution_pct=item.contribution_pct,
                contribution_share_pct=_round(
                    item.pnl / total_pnl * 100 if abs(total_pnl) > 1e-12 else 0.0
                ),
                buy_notional=item.buy_notional,
                sell_notional=item.sell_notional,
                final_value=item.final_value,
                fees=item.fees,
                final_weight_pct=item.final_weight_pct,
            )
        )

    return sorted(normalized, key=lambda item: abs(item.pnl), reverse=True)


def _group_contribution_by_sector(
    stock_contributions: list[StockContribution],
) -> dict[str, float]:
    grouped: dict[str, float] = {}
    for item in stock_contributions:
        grouped[item.sector] = grouped.get(item.sector, 0.0) + float(
            item.contribution_pct
        )
    return grouped


def _build_realized_weights(portfolio) -> pd.DataFrame:
    asset_values = portfolio.asset_value(group_by=False)
    if isinstance(asset_values, pd.Series):
        asset_values = asset_values.to_frame()
    if asset_values is None or asset_values.empty:
        return pd.DataFrame()

    total_value = portfolio.value()
    weights = asset_values.div(total_value, axis=0).fillna(0.0)
    row_sum = weights.sum(axis=1).replace(0.0, 1.0)
    return weights.div(row_sum, axis=0).fillna(0.0)


def _average_sector_weights(
    weights: pd.DataFrame,
    metadata: dict[str, dict[str, str]],
) -> dict[str, float]:
    if weights.empty:
        return {}

    grouped: dict[str, pd.Series] = {}
    for symbol in weights.columns:
        sector = metadata[str(symbol)]["sector"]
        grouped.setdefault(sector, pd.Series(0.0, index=weights.index, dtype=float))
        grouped[sector] = grouped[sector].add(
            weights[symbol].astype(float), fill_value=0.0
        )

    sector_weights = pd.DataFrame(grouped, index=weights.index).fillna(0.0)
    average_weights = sector_weights.mean(axis=0)
    total = float(average_weights.sum())
    if total > 0:
        average_weights = average_weights / total
    return {str(sector): float(weight) for sector, weight in average_weights.items()}


def _build_sector_summary(
    *,
    portfolio_sector_contrib: dict[str, float],
    benchmark_sector_contrib: dict[str, float],
    portfolio_sector_weights: dict[str, float],
    benchmark_sector_weights: dict[str, float],
) -> list[SectorAttributionSummary]:
    sectors = sorted(
        set(portfolio_sector_contrib)
        | set(benchmark_sector_contrib)
        | set(portfolio_sector_weights)
        | set(benchmark_sector_weights)
    )
    portfolio_total_return_pct = sum(portfolio_sector_contrib.values())
    benchmark_total_return_pct = sum(benchmark_sector_contrib.values())

    rows: list[SectorAttributionSummary] = []
    for sector in sectors:
        portfolio_weight = float(portfolio_sector_weights.get(sector, 0.0))
        benchmark_weight = float(benchmark_sector_weights.get(sector, 0.0))
        portfolio_contribution = float(portfolio_sector_contrib.get(sector, 0.0))
        benchmark_contribution = float(benchmark_sector_contrib.get(sector, 0.0))
        portfolio_return = (
            portfolio_contribution / portfolio_weight if portfolio_weight > 0 else 0.0
        )
        benchmark_return = (
            benchmark_contribution / benchmark_weight if benchmark_weight > 0 else 0.0
        )
        allocation_effect = (portfolio_weight - benchmark_weight) * (
            benchmark_return - benchmark_total_return_pct
        )
        selection_effect = benchmark_weight * (portfolio_return - benchmark_return)
        interaction_effect = (portfolio_weight - benchmark_weight) * (
            portfolio_return - benchmark_return
        )
        rows.append(
            SectorAttributionSummary(
                sector=sector,
                portfolio_weight_pct=_round(portfolio_weight * 100),
                benchmark_weight_pct=_round(benchmark_weight * 100),
                portfolio_return_pct=_round(portfolio_return),
                benchmark_return_pct=_round(benchmark_return),
                portfolio_contribution_pct=_round(portfolio_contribution),
                benchmark_contribution_pct=_round(benchmark_contribution),
                active_contribution_pct=_round(
                    portfolio_contribution - benchmark_contribution
                ),
                allocation_effect_pct=_round(allocation_effect),
                selection_effect_pct=_round(selection_effect),
                interaction_effect_pct=_round(interaction_effect),
            )
        )

    return sorted(
        rows, key=lambda item: abs(item.active_contribution_pct), reverse=True
    )


def _summary_to_sector_effect(
    item: SectorAttributionSummary,
    *,
    effect_pct: float,
) -> SectorAttribution:
    return SectorAttribution(
        sector=item.sector,
        effect_pct=_round(effect_pct),
        active_contribution_pct=item.active_contribution_pct,
        portfolio_weight_pct=item.portfolio_weight_pct,
        benchmark_weight_pct=item.benchmark_weight_pct,
        portfolio_return_pct=item.portfolio_return_pct,
        benchmark_return_pct=item.benchmark_return_pct,
        portfolio_contribution_pct=item.portfolio_contribution_pct,
        benchmark_contribution_pct=item.benchmark_contribution_pct,
    )


def _build_cost_breakdown(
    *,
    orders: pd.DataFrame,
    initial_cash: float,
) -> CostBreakdown:
    commission = float(orders["fees"].sum()) if not orders.empty else 0.0
    buy_notional = (
        float(orders.loc[orders["side"] == _BUY_SIDE, "notional"].sum())
        if not orders.empty
        else 0.0
    )
    sell_notional = (
        float(orders.loc[orders["side"] == _SELL_SIDE, "notional"].sum())
        if not orders.empty
        else 0.0
    )
    traded_notional = buy_notional + sell_notional
    total_cost = commission

    return CostBreakdown(
        commission=_round_money(commission),
        stamp_tax=0.0,
        slippage=0.0,
        total_cost=_round_money(total_cost),
        commission_share_pct=_round(
            commission / total_cost * 100 if total_cost > 0 else 0.0
        ),
        stamp_tax_share_pct=0.0,
        slippage_share_pct=0.0,
        cost_rate_pct=_round(
            total_cost / initial_cash * 100 if initial_cash > 0 else 0.0
        ),
        traded_notional=_round_money(traded_notional),
        turnover_pct=_round(
            traded_notional / initial_cash * 100 if initial_cash > 0 else 0.0
        ),
        cost_to_turnover_bps=_round(
            total_cost / traded_notional * 10_000 if traded_notional > 0 else 0.0
        ),
        buy_notional=_round_money(buy_notional),
        sell_notional=_round_money(sell_notional),
        orders_count=int(len(orders)),
    )


def _round(value: float | int | None, digits: int = 6) -> float:
    if value is None:
        return 0.0
    return round(float(value), digits)


def _round_money(value: float | int | None) -> float:
    return _round(value, digits=4)
