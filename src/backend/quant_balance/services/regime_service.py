"""市场状态识别服务。"""

from __future__ import annotations

from time import perf_counter

import pandas as pd

from quant_balance.core.regime import RegimeDetector, RegimeState
from quant_balance.data import load_dataframe
from quant_balance.logging_utils import get_logger, log_event
from quant_balance.services.symbol_search_service import BENCHMARK_INDEX_SYMBOLS

DEFAULT_REGIME_SYMBOL = "000300.SH"

logger = get_logger(__name__)


def run_market_regime_analysis(
    *,
    symbol: str = DEFAULT_REGIME_SYMBOL,
    start_date: str | None = None,
    end_date: str | None = None,
    data_provider: str | None = None,
) -> dict[str, object]:
    """返回指定指数当前状态或区间状态序列。"""

    detector = RegimeDetector()
    resolved_end = _normalize_date_text(end_date) or pd.Timestamp.now().date().isoformat()
    requested_start = _normalize_date_text(start_date) or resolved_end
    if pd.Timestamp(requested_start) > pd.Timestamp(resolved_end):
        raise ValueError("start_date 不能晚于 end_date")

    buffer_days = max(detector.long_window * 3, detector.momentum_window * 3, 180)
    load_start = (pd.Timestamp(requested_start) - pd.Timedelta(days=buffer_days)).date().isoformat()
    resolved_provider = data_provider or ("tushare" if symbol in BENCHMARK_INDEX_SYMBOLS else None)
    resolved_adjust = "none" if symbol in BENCHMARK_INDEX_SYMBOLS and resolved_provider == "tushare" else "qfq"

    started_at = perf_counter()
    load_kwargs = {
        "asset_type": "stock",
        "timeframe": "1d",
        "adjust": resolved_adjust,
    }
    if resolved_provider is not None:
        load_kwargs["provider"] = resolved_provider
    frame = load_dataframe(symbol, load_start, resolved_end, **load_kwargs)
    analysis = detector.analyze(frame)
    clipped = analysis.loc[
        (analysis.index >= pd.Timestamp(requested_start))
        & (analysis.index <= pd.Timestamp(resolved_end))
    ]
    if clipped.empty:
        raise ValueError(f"在 {requested_start} ~ {resolved_end} 期间未生成 {symbol} 的市场状态。")

    series = [_row_to_dict(index, row) for index, row in clipped.iterrows()]
    payload = {
        "symbol": symbol,
        "latest": series[-1],
        "series": series,
        "run_context": {
            "symbol": symbol,
            "start_date": requested_start,
            "end_date": resolved_end,
            "data_provider": frame.attrs.get("data_provider", resolved_provider),
            "short_window": detector.short_window,
            "long_window": detector.long_window,
            "momentum_window": detector.momentum_window,
            "trend_threshold": detector.trend_threshold,
            "momentum_threshold": detector.momentum_threshold,
        },
    }
    log_event(
        logger,
        "MARKET_REGIME",
        stage="service",
        symbol=symbol,
        start_date=requested_start,
        end_date=resolved_end,
        latest_regime=payload["latest"]["regime"],
        series_count=len(series),
        data_provider=frame.attrs.get("data_provider", resolved_provider),
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
    )
    return payload


def resolve_market_regime_filter(
    expected_regime: RegimeState,
    *,
    as_of_date: str,
    symbol: str = DEFAULT_REGIME_SYMBOL,
    data_provider: str | None = None,
) -> dict[str, object]:
    """计算市场状态过滤条件是否匹配。"""

    normalized_expected = str(expected_regime or "").strip().upper()
    if normalized_expected not in {"BULL", "BEAR", "SIDEWAYS"}:
        raise ValueError("market_regime 仅支持 BULL / BEAR / SIDEWAYS")

    payload = run_market_regime_analysis(
        symbol=symbol,
        end_date=as_of_date,
        data_provider=data_provider,
    )
    latest = payload["latest"]
    actual_regime = str(latest["regime"])
    return {
        "requested_regime": normalized_expected,
        "actual_regime": actual_regime,
        "matches": actual_regime == normalized_expected,
        "symbol": symbol,
        "date": latest["date"],
    }


def _row_to_dict(index: object, row: pd.Series) -> dict[str, object]:
    timestamp = pd.Timestamp(index)
    return {
        "date": timestamp.date().isoformat(),
        "regime": str(row["regime"]),
        "close": _round_or_none(row.get("close")),
        "short_ma": _round_or_none(row.get("short_ma")),
        "long_ma": _round_or_none(row.get("long_ma")),
        "trend_strength_pct": _round_or_none(row.get("trend_strength_pct")),
        "momentum_pct": _round_or_none(row.get("momentum_pct")),
    }


def _round_or_none(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), 6)


def _normalize_date_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return pd.Timestamp(text).date().isoformat()
