"""测试多因子打分引擎。"""

from __future__ import annotations

import pytest

from quant_balance.core.factors import rank_factor_items, resolve_factor_specs


def test_rank_factor_items_supports_mixed_directions_and_weight_normalization():
    items = [
        {"symbol": "AAA", "roe": 20.0, "pe": 10.0},
        {"symbol": "BBB", "roe": 15.0, "pe": 5.0},
        {"symbol": "CCC", "roe": 10.0, "pe": 20.0},
    ]

    result = rank_factor_items(
        items,
        [
            {"name": "roe", "weight": 6},
            {"name": "pe", "weight": 4},
        ],
    )

    assert list(result.rankings.index) == ["AAA", "BBB", "CCC"]
    assert result.normalized_weights == {"roe": 0.6, "pe": 0.4}
    assert pytest.approx(result.rankings.loc["AAA", "total_score"], rel=1e-4) == 86.6666667
    assert result.factor_directions == {"roe": "higher_better", "pe": "lower_better"}


def test_rank_factor_items_skips_symbols_with_missing_factor_values():
    items = [
        {"symbol": "AAA", "roe": 20.0, "pe": 10.0},
        {"symbol": "BBB", "roe": None, "pe": 5.0},
    ]

    result = rank_factor_items(
        items,
        [
            {"name": "roe", "weight": 0.5},
            {"name": "pe", "weight": 0.5},
        ],
    )

    assert list(result.rankings.index) == ["AAA"]
    assert result.skipped_symbols == ["BBB"]


def test_rank_factor_items_allows_partial_coverage_when_threshold_is_lowered():
    items = [
        {"symbol": "AAA", "roe": 20.0, "pe": 10.0},
        {"symbol": "BBB", "roe": None, "pe": 5.0},
    ]

    result = rank_factor_items(
        items,
        [
            {"name": "roe", "weight": 0.5},
            {"name": "pe", "weight": 0.5},
        ],
        min_factor_coverage=0.5,
    )

    assert list(result.rankings.index) == ["AAA", "BBB"]
    assert result.skipped_symbols == []


def test_resolve_factor_specs_rejects_invalid_input():
    with pytest.raises(ValueError, match="未知因子"):
        resolve_factor_specs([{"name": "unknown_factor"}])

    with pytest.raises(ValueError, match="因子不能重复"):
        resolve_factor_specs([{"name": "roe"}, {"name": "roe"}])
