"""多因子打分与排名引擎。

功能：
- 内置多种基本面因子（PE、PB、ROE 等）
- 支持自定义因子权重和方向
- 对候选股票进行标准化打分和排名

因子方向：
- higher_better: 数值越大越好（如 ROE）
- lower_better: 数值越小越好（如 PE）

使用方法：
    from quant_balance.core.factors import rank_factor_items, DEFAULT_FACTOR_SPECS
    result = rank_factor_items(candidates, DEFAULT_FACTOR_SPECS)
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
import math

import pandas as pd

FactorDirection = str


@dataclass(frozen=True, slots=True)
class FactorDefinition:
    """单个因子定义。"""

    name: str
    description: str
    default_direction: FactorDirection
    compute: Callable[[Mapping[str, object]], float | None]


@dataclass(frozen=True, slots=True)
class FactorSpec:
    """单个因子配置。"""

    name: str
    weight: float = 1.0
    direction: FactorDirection | None = None


@dataclass(slots=True)
class FactorRankingResult:
    """因子排名结果。"""

    rankings: pd.DataFrame
    raw_values: pd.DataFrame
    scores: pd.DataFrame
    normalized_weights: dict[str, float]
    factor_directions: dict[str, FactorDirection]
    skipped_symbols: list[str]


def _to_optional_float(value: object) -> float | None:
    if value is None:
        return None

    item = getattr(value, "item", None)
    if callable(item):
        try:
            value = item()
        except (TypeError, ValueError):
            pass

    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"nan", "none", "nat"}:
            return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _field_factor(
    field_name: str,
    *,
    direction: FactorDirection,
    description: str,
) -> FactorDefinition:
    return FactorDefinition(
        name=field_name,
        description=description,
        default_direction=direction,
        compute=lambda row, field_name=field_name: _to_optional_float(
            row.get(field_name)
        ),
    )


def _derived_factor(
    name: str,
    *,
    direction: FactorDirection,
    description: str,
    compute: Callable[[Mapping[str, object]], float | None],
) -> FactorDefinition:
    return FactorDefinition(
        name=name,
        description=description,
        default_direction=direction,
        compute=compute,
    )


def _safe_ratio(numerator: object, denominator: object) -> float | None:
    left = _to_optional_float(numerator)
    right = _to_optional_float(denominator)
    if left is None or right is None or right == 0:
        return None
    return left / right


FACTOR_REGISTRY: dict[str, FactorDefinition] = {
    factor.name: factor
    for factor in (
        _field_factor("pe", direction="lower_better", description="市盈率（越低越好）"),
        _field_factor(
            "pe_ttm", direction="lower_better", description="滚动市盈率（越低越好）"
        ),
        _field_factor("pb", direction="lower_better", description="市净率（越低越好）"),
        _field_factor("ps", direction="lower_better", description="市销率（越低越好）"),
        _field_factor(
            "ps_ttm", direction="lower_better", description="滚动市销率（越低越好）"
        ),
        _field_factor(
            "dv_ratio", direction="higher_better", description="股息率（越高越好）"
        ),
        _field_factor(
            "dv_ttm", direction="higher_better", description="TTM 股息率（越高越好）"
        ),
        _field_factor("roe", direction="higher_better", description="ROE（越高越好）"),
        _field_factor(
            "roe_dt", direction="higher_better", description="扣非 ROE（越高越好）"
        ),
        _field_factor("roa", direction="higher_better", description="ROA（越高越好）"),
        _field_factor(
            "grossprofit_margin",
            direction="higher_better",
            description="毛利率（越高越好）",
        ),
        _field_factor(
            "netprofit_margin",
            direction="higher_better",
            description="净利率（越高越好）",
        ),
        _field_factor(
            "current_ratio",
            direction="higher_better",
            description="流动比率（越高越好）",
        ),
        _field_factor(
            "quick_ratio", direction="higher_better", description="速动比率（越高越好）"
        ),
        _field_factor(
            "assets_turn",
            direction="higher_better",
            description="总资产周转率（越高越好）",
        ),
        _field_factor(
            "eps", direction="higher_better", description="每股收益（越高越好）"
        ),
        _field_factor(
            "bps", direction="higher_better", description="每股净资产（越高越好）"
        ),
        _derived_factor(
            "market_cap",
            direction="lower_better",
            description="总市值因子，默认偏好更小市值",
            compute=lambda row: _to_optional_float(row.get("total_mv")),
        ),
        _derived_factor(
            "debt_to_assets",
            direction="lower_better",
            description="资产负债率（越低越好）",
            compute=lambda row: _safe_ratio(
                row.get("total_liab"), row.get("total_assets")
            ),
        ),
        _derived_factor(
            "cashflow_to_profit",
            direction="higher_better",
            description="经营现金流 / 净利润（越高越好）",
            compute=lambda row: _safe_ratio(
                row.get("n_cashflow_act"), row.get("net_profit")
            ),
        ),
        _derived_factor(
            "profit_to_assets",
            direction="higher_better",
            description="净利润 / 总资产（越高越好）",
            compute=lambda row: _safe_ratio(
                row.get("net_profit"), row.get("total_assets")
            ),
        ),
    )
}

DEFAULT_FACTOR_SPECS: tuple[FactorSpec, ...] = (
    FactorSpec(name="roe", weight=0.4),
    FactorSpec(name="pe", weight=0.25),
    FactorSpec(name="pb", weight=0.2),
    FactorSpec(name="dv_ratio", weight=0.15),
)


def list_factor_definitions() -> list[dict[str, str]]:
    """返回可用因子定义。"""

    return [
        {
            "name": factor.name,
            "description": factor.description,
            "default_direction": factor.default_direction,
        }
        for factor in FACTOR_REGISTRY.values()
    ]


def resolve_factor_specs(
    specs: Sequence[FactorSpec | Mapping[str, object]] | None = None,
) -> list[FactorSpec]:
    """校验并规范化因子配置。"""

    raw_specs = list(specs or DEFAULT_FACTOR_SPECS)
    if not raw_specs:
        raise ValueError("factors 不能为空")

    normalized_specs: list[FactorSpec] = []
    total_weight = 0.0
    seen_names: set[str] = set()
    for raw in raw_specs:
        if isinstance(raw, FactorSpec):
            spec = raw
        else:
            spec = FactorSpec(
                name=str(raw.get("name", "")).strip(),
                weight=float(raw.get("weight", 1.0)),
                direction=str(raw["direction"]).strip()
                if raw.get("direction") is not None
                else None,
            )

        if spec.name not in FACTOR_REGISTRY:
            raise ValueError(f"未知因子: {spec.name}，可用: {sorted(FACTOR_REGISTRY)}")
        if spec.weight <= 0:
            raise ValueError("因子权重必须 > 0")
        if spec.name in seen_names:
            raise ValueError(f"因子不能重复: {spec.name}")

        direction = spec.direction or FACTOR_REGISTRY[spec.name].default_direction
        if direction not in {"higher_better", "lower_better"}:
            raise ValueError("direction 仅支持 higher_better / lower_better")

        normalized_specs.append(
            FactorSpec(name=spec.name, weight=float(spec.weight), direction=direction)
        )
        total_weight += float(spec.weight)
        seen_names.add(spec.name)

    if total_weight <= 0:
        raise ValueError("因子权重和必须 > 0")
    return normalized_specs


def standardize_factor_series(
    series: pd.Series,
    *,
    direction: FactorDirection,
) -> pd.Series:
    """把原始因子值标准化为 0~100 分。"""

    clean = series.dropna()
    if clean.empty:
        return pd.Series(index=series.index, dtype=float)
    if len(clean) == 1:
        only_symbol = clean.index[0]
        result = pd.Series(index=series.index, dtype=float)
        result.loc[only_symbol] = 100.0
        return result

    ascending = direction == "higher_better"
    ranked = clean.rank(method="average", pct=True, ascending=ascending) * 100.0
    result = pd.Series(index=series.index, dtype=float)
    result.loc[ranked.index] = ranked
    return result


def build_factor_matrix(
    items: Iterable[Mapping[str, object]],
    factor_specs: Sequence[FactorSpec | Mapping[str, object]] | None = None,
) -> pd.DataFrame:
    """从候选样本构建原始因子矩阵。"""

    resolved_specs = resolve_factor_specs(factor_specs)
    rows: dict[str, dict[str, float | None]] = {}
    for item in items:
        symbol = str(item.get("symbol") or item.get("ts_code") or "").strip()
        if not symbol:
            raise ValueError("factor item 缺少 symbol / ts_code")
        rows[symbol] = {
            spec.name: FACTOR_REGISTRY[spec.name].compute(item)
            for spec in resolved_specs
        }

    if not rows:
        return pd.DataFrame(columns=[spec.name for spec in resolved_specs], dtype=float)
    return pd.DataFrame.from_dict(rows, orient="index")


def rank_factor_items(
    items: Iterable[Mapping[str, object]],
    factor_specs: Sequence[FactorSpec | Mapping[str, object]] | None = None,
    *,
    min_factor_coverage: float = 0.5,
) -> FactorRankingResult:
    """对候选样本做多因子标准化与加权打分。

    参数:
        min_factor_coverage: 至少有多少比例的因子非空才参与排名 (0~1)，默认 0.5
    """

    resolved_specs = resolve_factor_specs(factor_specs)
    raw_values = build_factor_matrix(items, resolved_specs)
    if raw_values.empty:
        return FactorRankingResult(
            rankings=pd.DataFrame(columns=["total_score", "rank"]),
            raw_values=raw_values,
            scores=pd.DataFrame(
                columns=[spec.name for spec in resolved_specs], dtype=float
            ),
            normalized_weights=_normalize_weights(resolved_specs),
            factor_directions={
                spec.name: str(spec.direction) for spec in resolved_specs
            },
            skipped_symbols=[],
        )

    factor_count = len(resolved_specs)
    coverage = raw_values.notna().sum(axis=1) / factor_count
    coverage_mask = coverage >= min_factor_coverage
    skipped_symbols = raw_values.index[~coverage_mask].tolist()
    scored_raw_values = raw_values.loc[coverage_mask].copy()
    if scored_raw_values.empty:
        return FactorRankingResult(
            rankings=pd.DataFrame(columns=["total_score", "rank"]),
            raw_values=raw_values,
            scores=pd.DataFrame(
                columns=[spec.name for spec in resolved_specs], dtype=float
            ),
            normalized_weights=_normalize_weights(resolved_specs),
            factor_directions={
                spec.name: str(spec.direction) for spec in resolved_specs
            },
            skipped_symbols=skipped_symbols,
        )

    scores = pd.DataFrame(index=scored_raw_values.index)
    for spec in resolved_specs:
        scores[spec.name] = standardize_factor_series(
            scored_raw_values[spec.name],
            direction=str(spec.direction),
        )

    normalized_weights = _normalize_weights(resolved_specs)
    total_score = pd.Series(0.0, index=scores.index)
    weight_sum = pd.Series(0.0, index=scores.index)
    for spec in resolved_specs:
        factor_scores = scores[spec.name]
        valid_mask = factor_scores.notna()
        total_score = total_score + factor_scores.fillna(0.0) * normalized_weights[spec.name]
        weight_sum = weight_sum + valid_mask.astype(float) * normalized_weights[spec.name]

    # 按实际参与打分的权重归一化
    total_score = total_score / weight_sum.replace(0.0, 1.0) * weight_sum.clip(upper=1.0).replace(0.0, 1.0)

    rankings = pd.DataFrame({"total_score": total_score})
    rankings = rankings.sort_values("total_score", ascending=False)
    rankings["rank"] = range(1, len(rankings) + 1)
    return FactorRankingResult(
        rankings=rankings,
        raw_values=raw_values,
        scores=scores,
        normalized_weights=normalized_weights,
        factor_directions={spec.name: str(spec.direction) for spec in resolved_specs},
        skipped_symbols=skipped_symbols,
    )


def _normalize_weights(specs: Sequence[FactorSpec]) -> dict[str, float]:
    total = sum(spec.weight for spec in specs)
    return {spec.name: spec.weight / total for spec in specs}
