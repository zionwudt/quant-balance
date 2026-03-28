"""回测服务 — 编排数据加载与引擎执行。

功能：
- 单股回测 (run_single_backtest): 加载数据 → 执行回测 → 生成报告
- 参数优化 (run_optimize): 参数扫描 + Walk-Forward 分析

调用链：
backtest_service.run_single_backtest()
  ├── data.market_loader.load_dataframe()
  ├── core.backtest.run_backtest()
  └── core.report.normalize_bt_stats() → 生成图表数据

backtest_service.run_optimize()
  ├── data.market_loader.load_dataframe()
  ├── core.backtest.optimize()
  └── _run_walk_forward() → Walk-Forward 分析
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from math import isfinite
from operator import eq, ge, gt, le, lt, ne
from time import perf_counter

import pandas as pd

from quant_balance.core.backtest import optimize, run_backtest
from quant_balance.core.indicators import bollinger, ema, sma
from quant_balance.core.report import (
    bt_trades_to_dicts,
    equity_curve_to_dicts,
    normalize_bt_stats,
)
from quant_balance.core.strategies import STRATEGY_REGISTRY
from quant_balance.data import load_dataframe
from quant_balance.logging_utils import get_logger, log_event
from quant_balance.services.symbol_search_service import BENCHMARK_INDEX_SYMBOLS

logger = get_logger(__name__)

LONG_TASK_RUN_THRESHOLD = 300
CONSTRAINT_OPERATORS: dict[str, Callable[[object, object], bool]] = {
    "<": lt,
    "<=": le,
    ">": gt,
    ">=": ge,
    "==": eq,
    "!=": ne,
}


def run_single_backtest(
    *,
    symbol: str,
    start_date: str,
    end_date: str,
    asset_type: str = "stock",
    timeframe: str = "1d",
    strategy: str = "sma_cross",
    cash: float = 100_000.0,
    commission: float = 0.001,
    slippage_mode: str = "off",
    slippage_rate: float = 0.0,
    params: dict | None = None,
    data_provider: str | None = None,
    benchmark_symbol: str | None = None,
    benchmark_asset_type: str | None = None,
    benchmark_data_provider: str | None = None,
) -> dict:
    """执行单股精细回测，返回 API 可直接消费的结果字典。"""
    strategy_cls = STRATEGY_REGISTRY.get(strategy)
    if strategy_cls is None:
        raise ValueError(f"未知策略: {strategy}，可用: {list(STRATEGY_REGISTRY)}")

    effective_commission, spread = _resolve_execution_costs(
        commission=commission,
        slippage_mode=slippage_mode,
        slippage_rate=slippage_rate,
    )
    started_at = perf_counter()
    df = _load_market_dataframe(
        symbol,
        start_date,
        end_date,
        asset_type=asset_type,
        timeframe=timeframe,
        data_provider=data_provider,
        adjust="qfq" if timeframe == "1d" else "none",
    )
    benchmark_df = None
    resolved_benchmark_asset_type = benchmark_asset_type or (
        "stock" if benchmark_symbol in BENCHMARK_INDEX_SYMBOLS else asset_type
    )
    resolved_benchmark_data_provider = (
        benchmark_data_provider
        if benchmark_data_provider is not None
        else (
            "tushare" if benchmark_symbol in BENCHMARK_INDEX_SYMBOLS else data_provider
        )
    )
    resolved_benchmark_adjust = (
        "none"
        if (
            benchmark_symbol in BENCHMARK_INDEX_SYMBOLS
            and resolved_benchmark_data_provider == "tushare"
        )
        else "qfq"
    )
    if benchmark_symbol is not None:
        benchmark_df = _load_market_dataframe(
            benchmark_symbol,
            start_date,
            end_date,
            asset_type=resolved_benchmark_asset_type,
            timeframe=timeframe,
            data_provider=resolved_benchmark_data_provider,
            adjust=resolved_benchmark_adjust if timeframe == "1d" else "none",
        )

    result = run_backtest(
        df,
        strategy_cls,
        cash=cash,
        spread=spread,
        commission=effective_commission,
        strategy_params=params,
        log_context={
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "asset_type": asset_type,
            "strategy": strategy,
            "timeframe": df.attrs.get("timeframe", timeframe),
            "data_provider": df.attrs.get("data_provider", data_provider),
        },
    )
    summary = normalize_bt_stats(
        result.stats,
        risk_params=params,
        benchmark_df=benchmark_df,
        benchmark_symbol=benchmark_symbol,
    )
    chart_payload = _build_chart_payload(
        df,
        result.trades,
        strategy=strategy,
        params=params,
    )

    payload = {
        "summary": summary,
        "trades": bt_trades_to_dicts(result.trades, params),
        "equity_curve": equity_curve_to_dicts(
            result.equity_curve, benchmark_df=benchmark_df
        ),
        **chart_payload,
        "run_context": {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "asset_type": df.attrs.get("asset_type", asset_type),
            "strategy": strategy,
            "timeframe": df.attrs.get("timeframe", timeframe),
            "cash": cash,
            "commission": commission,
            "effective_commission": effective_commission,
            "spread": spread,
            "slippage_mode": slippage_mode,
            "slippage_rate": slippage_rate,
            "price_adjustment": df.attrs.get(
                "price_adjustment", "qfq" if timeframe == "1d" else "none"
            ),
            "params": params or {},
            "bars_count": len(df),
            "data_provider": df.attrs.get("data_provider", data_provider),
            "benchmark_symbol": benchmark_symbol,
            "benchmark_asset_type": (
                benchmark_df.attrs.get("asset_type", resolved_benchmark_asset_type)
                if benchmark_df is not None
                else None
            ),
            "benchmark_data_provider": (
                benchmark_df.attrs.get(
                    "data_provider", resolved_benchmark_data_provider
                )
                if benchmark_df is not None
                else None
            ),
        },
    }
    log_event(
        logger,
        "BACKTEST_RUN",
        stage="service",
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        asset_type=df.attrs.get("asset_type", asset_type),
        strategy=strategy,
        timeframe=df.attrs.get("timeframe", timeframe),
        cash=cash,
        commission=commission,
        effective_commission=effective_commission,
        spread=spread,
        slippage_mode=slippage_mode,
        slippage_rate=slippage_rate,
        price_adjustment=df.attrs.get(
            "price_adjustment", "qfq" if timeframe == "1d" else "none"
        ),
        params=params or {},
        bars_count=len(df),
        trades_count=len(result.trades),
        data_provider=df.attrs.get("data_provider", data_provider),
        benchmark_symbol=benchmark_symbol,
        benchmark_asset_type=(
            benchmark_df.attrs.get("asset_type", resolved_benchmark_asset_type)
            if benchmark_df is not None
            else None
        ),
        benchmark_data_provider=(
            benchmark_df.attrs.get("data_provider", resolved_benchmark_data_provider)
            if benchmark_df is not None
            else None
        ),
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
    )
    return payload


def _resolve_execution_costs(
    *,
    commission: float,
    slippage_mode: str,
    slippage_rate: float,
) -> tuple[float, float]:
    if slippage_rate < 0:
        raise ValueError("slippage_rate 必须 >= 0")
    if slippage_mode == "off":
        return commission, 0.0
    if slippage_mode == "spread":
        return commission, slippage_rate
    if slippage_mode == "commission":
        return commission + slippage_rate, 0.0
    raise ValueError("slippage_mode 必须是 off / spread / commission")


def run_optimize(
    *,
    symbol: str,
    start_date: str,
    end_date: str,
    asset_type: str = "stock",
    strategy: str = "sma_cross",
    cash: float = 100_000.0,
    commission: float = 0.001,
    maximize: str = "Sharpe Ratio",
    param_ranges: dict | None = None,
    top_n: int = 5,
    constraints: list[dict] | None = None,
    walk_forward: dict | None = None,
    data_provider: str | None = None,
) -> dict:
    """执行参数优化，返回最优参数、排名结果和 Walk-Forward 输出。"""
    strategy_cls = STRATEGY_REGISTRY.get(strategy)
    if strategy_cls is None:
        raise ValueError(f"未知策略: {strategy}，可用: {list(STRATEGY_REGISTRY)}")

    if not param_ranges:
        raise ValueError("param_ranges 不能为空")

    normalized_param_ranges, strategy_params = _normalize_param_ranges(
        strategy_cls, param_ranges
    )
    normalized_constraints = _normalize_constraints(constraints or [], strategy_params)
    constraint_fn = _build_constraint(normalized_constraints)
    walk_forward_config = _normalize_walk_forward_config(walk_forward)

    started_at = perf_counter()
    df = _load_market_dataframe(
        symbol,
        start_date,
        end_date,
        asset_type=asset_type,
        timeframe="1d",
        data_provider=data_provider,
        adjust="qfq",
    )
    walk_forward_windows = _count_walk_forward_windows(len(df), walk_forward_config)

    optimize_result = optimize(
        df,
        strategy_cls,
        cash=cash,
        commission=commission,
        maximize=maximize,
        constraint=constraint_fn,
        top_n=top_n,
        log_context={
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "asset_type": asset_type,
            "strategy": strategy,
            "timeframe": "1d",
            "data_provider": df.attrs.get("data_provider", data_provider),
        },
        **normalized_param_ranges,
    )
    execution = _build_execution_payload(
        optimize_result.candidate_count, walk_forward_windows
    )

    payload = {
        "best_params": _jsonable_value(optimize_result.best_params),
        "best_stats": normalize_bt_stats(
            optimize_result.best_stats, risk_params=optimize_result.best_params
        ),
        "top_results": _jsonable_value(optimize_result.top_results),
        "execution": execution,
        "run_context": {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "asset_type": df.attrs.get("asset_type", asset_type),
            "strategy": strategy,
            "maximize": maximize,
            "param_ranges": _jsonable_value(normalized_param_ranges),
            "top_n": top_n,
            "constraints": _jsonable_value(normalized_constraints),
            "walk_forward": _jsonable_value(walk_forward_config),
            "bars_count": len(df),
            "data_provider": df.attrs.get("data_provider", data_provider),
        },
    }
    if walk_forward_config is not None:
        payload["walk_forward"] = _run_walk_forward(
            df=df,
            strategy_cls=strategy_cls,
            cash=cash,
            commission=commission,
            maximize=maximize,
            param_ranges=normalized_param_ranges,
            constraint=constraint_fn,
            walk_forward_config=walk_forward_config,
            log_context={
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "asset_type": asset_type,
                "strategy": strategy,
                "timeframe": "1d",
                "data_provider": df.attrs.get("data_provider", data_provider),
            },
        )
    log_event(
        logger,
        "BACKTEST_OPTIMIZE",
        stage="service",
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        asset_type=df.attrs.get("asset_type", asset_type),
        strategy=strategy,
        maximize=maximize,
        param_ranges=_jsonable_value(normalized_param_ranges),
        top_n=top_n,
        constraints=_jsonable_value(normalized_constraints),
        best_params=_jsonable_value(optimize_result.best_params),
        candidate_count=optimize_result.candidate_count,
        walk_forward_windows=walk_forward_windows,
        async_recommended=execution["async_recommended"],
        estimated_total_runs=execution["estimated_total_runs"],
        data_provider=df.attrs.get("data_provider", data_provider),
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
    )
    return payload


def _load_market_dataframe(
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    asset_type: str,
    timeframe: str,
    data_provider: str | None,
    adjust: str,
) -> pd.DataFrame:
    load_kwargs = {"asset_type": asset_type, "timeframe": timeframe, "adjust": adjust}
    if data_provider is not None:
        load_kwargs["provider"] = data_provider
    return load_dataframe(symbol, start_date, end_date, **load_kwargs)


def _build_chart_payload(
    df: pd.DataFrame,
    trades_df: pd.DataFrame,
    *,
    strategy: str,
    params: dict | None,
) -> dict[str, object]:
    return {
        "price_bars": _price_bars_to_dicts(df),
        "chart_overlays": {
            "line_series": _chart_line_series(df, strategy=strategy, params=params),
            "trade_markers": _trade_markers_to_dicts(trades_df),
        },
    }


def _price_bars_to_dicts(df: pd.DataFrame) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for index, row in df.iterrows():
        records.append(
            {
                "date": _format_time_label(index),
                "open": float(row.get("Open", 0.0)),
                "high": float(row.get("High", 0.0)),
                "low": float(row.get("Low", 0.0)),
                "close": float(row.get("Close", 0.0)),
                "volume": float(row.get("Volume", 0.0)),
            }
        )
    return records


def _trade_markers_to_dicts(trades_df: pd.DataFrame | None) -> list[dict[str, object]]:
    if trades_df is None or trades_df.empty:
        return []

    markers: list[dict[str, object]] = []
    for trade_index, (_, row) in enumerate(trades_df.iterrows(), start=1):
        entry_bar = int(row.get("EntryBar", 0))
        exit_bar = int(row.get("ExitBar", 0))
        entry_time = _format_trade_time(row.get("EntryTime", ""))
        exit_time = _format_trade_time(row.get("ExitTime", ""))
        markers.append(
            {
                "trade_index": trade_index,
                "side": "buy",
                "label": f"B{trade_index}",
                "date": entry_time,
                "price": float(row.get("EntryPrice", 0.0)),
                "bar_index": entry_bar,
            }
        )
        markers.append(
            {
                "trade_index": trade_index,
                "side": "sell",
                "label": f"S{trade_index}",
                "date": exit_time,
                "price": float(row.get("ExitPrice", 0.0)),
                "bar_index": exit_bar,
            }
        )
    return markers


def _format_time_label(value: object) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.hour == 0 and timestamp.minute == 0 and timestamp.second == 0:
        return timestamp.date().isoformat()
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def _format_trade_time(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return _format_time_label(text)
    except Exception:  # noqa: BLE001
        return text


def _chart_line_series(
    df: pd.DataFrame,
    *,
    strategy: str,
    params: dict | None,
) -> list[dict[str, object]]:
    close = df["Close"]
    resolved_params = _resolve_chart_params(strategy, params)

    if strategy == "sma_cross":
        return [
            _line_series(
                f"SMA {resolved_params['fast_period']}",
                sma(close, int(resolved_params["fast_period"])),
                "#34d399",
            ),
            _line_series(
                f"SMA {resolved_params['slow_period']}",
                sma(close, int(resolved_params["slow_period"])),
                "#f59e0b",
            ),
        ]
    if strategy == "ema_cross":
        return [
            _line_series(
                f"EMA {resolved_params['fast_period']}",
                ema(close, int(resolved_params["fast_period"])),
                "#22c55e",
            ),
            _line_series(
                f"EMA {resolved_params['slow_period']}",
                ema(close, int(resolved_params["slow_period"])),
                "#f59e0b",
            ),
        ]
    if strategy == "macd":
        return [
            _line_series(
                f"EMA {resolved_params['fast_period']}",
                ema(close, int(resolved_params["fast_period"])),
                "#22c55e",
            ),
            _line_series(
                f"EMA {resolved_params['slow_period']}",
                ema(close, int(resolved_params["slow_period"])),
                "#f59e0b",
            ),
        ]
    if strategy == "bollinger":
        upper, middle, lower = bollinger(
            close,
            int(resolved_params["period"]),
            float(resolved_params["num_std"]),
        )
        return [
            _line_series("BOLL Upper", upper, "#60a5fa", "dashed"),
            _line_series("BOLL Mid", middle, "#f59e0b"),
            _line_series("BOLL Lower", lower, "#60a5fa", "dashed"),
        ]
    if strategy == "grid":
        anchor = sma(close, int(resolved_params["anchor_period"]))
        grid_pct = float(resolved_params["grid_pct"])
        return [
            _line_series(
                f"Anchor {resolved_params['anchor_period']}", anchor, "#f59e0b"
            ),
            _line_series("Grid Upper", anchor * (1 + grid_pct), "#60a5fa", "dashed"),
            _line_series("Grid Lower", anchor * (1 - grid_pct), "#60a5fa", "dashed"),
        ]
    if strategy == "ma_rsi_filter":
        return [
            _line_series(
                f"SMA {resolved_params['fast_period']}",
                sma(close, int(resolved_params["fast_period"])),
                "#34d399",
            ),
            _line_series(
                f"SMA {resolved_params['slow_period']}",
                sma(close, int(resolved_params["slow_period"])),
                "#f59e0b",
            ),
        ]
    return []


def _resolve_chart_params(strategy: str, params: dict | None) -> dict[str, object]:
    strategy_cls = STRATEGY_REGISTRY[strategy]
    defaults = _strategy_param_defaults(strategy_cls)
    return {**defaults, **(params or {})}


def _line_series(
    name: str,
    values: pd.Series,
    color: str,
    style: str = "solid",
) -> dict[str, object]:
    return {
        "name": name,
        "color": color,
        "style": style,
        "values": [
            None if pd.isna(value) else round(float(value), 6)
            for value in pd.Series(values).tolist()
        ],
    }


def _normalize_param_ranges(
    strategy_cls: type,
    param_ranges: dict,
) -> tuple[dict[str, list[object]], dict[str, object]]:
    strategy_params = _strategy_param_defaults(strategy_cls)
    unknown_params = sorted(set(param_ranges) - set(strategy_params))
    if unknown_params:
        raise ValueError(
            f"param_ranges 包含未知参数: {unknown_params}，可用参数: {sorted(strategy_params)}"
        )

    normalized: dict[str, list[object]] = {}
    for name, raw_values in param_ranges.items():
        if isinstance(raw_values, (str, bytes)) or not isinstance(raw_values, Iterable):
            raise ValueError(f"参数 {name} 的候选值必须是非字符串可迭代对象")

        values = list(raw_values)
        if not values:
            raise ValueError(f"参数 {name} 的候选值不能为空")
        for value in values:
            _validate_candidate_value(name, value, strategy_params[name])
        normalized[name] = values
    return normalized, strategy_params


def _strategy_param_defaults(strategy_cls: type) -> dict[str, object]:
    params: dict[str, object] = {}
    for base in reversed(strategy_cls.mro()):
        if base.__name__ in {"object", "Strategy"}:
            continue
        for key, value in vars(base).items():
            if key.startswith("_") or key == "qb_exclusive_orders" or callable(value):
                continue
            if isinstance(value, (classmethod, staticmethod, property)):
                continue
            if isinstance(value, (bool, int, float, str)):
                params[key] = value
    return params


def _validate_candidate_value(param_name: str, value: object, default: object) -> None:
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        raise ValueError(f"参数 {param_name} 的候选值必须是标量")

    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise ValueError(f"参数 {param_name} 的候选值必须是布尔类型")
        return

    if isinstance(default, int):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"参数 {param_name} 的候选值必须是整数类型")
        return

    if isinstance(default, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"参数 {param_name} 的候选值必须是数值类型")
        if not isfinite(float(value)):
            raise ValueError(f"参数 {param_name} 的候选值必须是有限数值")
        return

    if isinstance(default, str) and not isinstance(value, str):
        raise ValueError(f"参数 {param_name} 的候选值必须是字符串类型")


def _normalize_constraints(
    constraints: list[dict],
    strategy_params: dict[str, object],
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for item in constraints:
        left = str(item["left"])
        if left not in strategy_params:
            raise ValueError(f"constraints 引用了未知参数: {left}")

        operator_symbol = str(item["operator"])
        if operator_symbol not in CONSTRAINT_OPERATORS:
            raise ValueError(f"不支持的约束操作符: {operator_symbol}")

        if "right_param" in item:
            right_param = str(item["right_param"])
            if right_param not in strategy_params:
                raise ValueError(f"constraints 引用了未知参数: {right_param}")
            normalized.append(
                {
                    "left": left,
                    "operator": operator_symbol,
                    "right_param": right_param,
                }
            )
            continue

        right_value = item["right_value"]
        _validate_candidate_value(left, right_value, strategy_params[left])
        normalized.append(
            {
                "left": left,
                "operator": operator_symbol,
                "right_value": right_value,
            }
        )
    return normalized


def _build_constraint(
    constraints: list[dict[str, object]],
) -> Callable[[object], bool] | None:
    if not constraints:
        return None

    def constraint(params: object) -> bool:
        for item in constraints:
            left_value = getattr(params, str(item["left"]))
            if "right_param" in item:
                right_value = getattr(params, str(item["right_param"]))
            else:
                right_value = item["right_value"]
            if not CONSTRAINT_OPERATORS[str(item["operator"])](left_value, right_value):
                return False
        return True

    return constraint


def _normalize_walk_forward_config(
    walk_forward: dict | None,
) -> dict[str, object] | None:
    if walk_forward is None:
        return None

    config = dict(walk_forward)
    config["step_bars"] = int(config.get("step_bars") or config["test_bars"])
    if config["step_bars"] < 1:
        raise ValueError("walk_forward.step_bars 必须 >= 1")
    return config


def _count_walk_forward_windows(
    total_bars: int,
    walk_forward_config: dict[str, object] | None,
) -> int:
    if walk_forward_config is None:
        return 0
    return len(_iter_walk_forward_slices(total_bars, walk_forward_config))


def _iter_walk_forward_slices(
    total_bars: int,
    walk_forward_config: dict[str, object],
) -> list[tuple[int, int, int, int]]:
    train_bars = int(walk_forward_config["train_bars"])
    test_bars = int(walk_forward_config["test_bars"])
    step_bars = int(walk_forward_config["step_bars"])
    anchored = bool(walk_forward_config.get("anchored", False))

    if total_bars < train_bars + test_bars:
        raise ValueError(
            f"Walk-Forward 至少需要 {train_bars + test_bars} 根K线，当前仅有 {total_bars} 根"
        )

    windows: list[tuple[int, int, int, int]] = []
    offset = 0
    while True:
        if anchored:
            train_start = 0
            train_end = train_bars + offset
        else:
            train_start = offset
            train_end = offset + train_bars

        test_start = train_end
        test_end = test_start + test_bars
        if test_end > total_bars:
            break
        windows.append((train_start, train_end, test_start, test_end))
        offset += step_bars
    return windows


def _run_walk_forward(
    *,
    df: pd.DataFrame,
    strategy_cls: type,
    cash: float,
    commission: float,
    maximize: str,
    param_ranges: dict[str, list[object]],
    constraint: Callable[[object], bool] | None,
    walk_forward_config: dict[str, object],
    log_context: dict[str, object],
) -> dict[str, object]:
    windows: list[dict[str, object]] = []
    for index, (train_start, train_end, test_start, test_end) in enumerate(
        _iter_walk_forward_slices(len(df), walk_forward_config),
        start=1,
    ):
        train_df = df.iloc[train_start:train_end]
        test_df = df.iloc[test_start:test_end]
        optimize_result = optimize(
            train_df,
            strategy_cls,
            cash=cash,
            commission=commission,
            maximize=maximize,
            constraint=constraint,
            top_n=1,
            log_context={
                **log_context,
                "walk_forward_window": index,
                "sample": "in_sample",
            },
            **param_ranges,
        )
        out_sample = run_backtest(
            test_df,
            strategy_cls,
            cash=cash,
            commission=commission,
            strategy_params=optimize_result.best_params,
            log_context={
                **log_context,
                "walk_forward_window": index,
                "sample": "out_of_sample",
            },
        )
        windows.append(
            {
                "window_index": index,
                "train_period": _frame_period_summary(train_df),
                "test_period": _frame_period_summary(test_df),
                "best_params": _jsonable_value(optimize_result.best_params),
                "in_sample": normalize_bt_stats(
                    optimize_result.best_stats, risk_params=optimize_result.best_params
                ),
                "out_of_sample": out_sample.report,
            }
        )

    return {
        "config": _jsonable_value(walk_forward_config),
        "windows_count": len(windows),
        "averages": {
            "in_sample": _average_numeric_report_fields(
                [item["in_sample"] for item in windows]
            ),
            "out_of_sample": _average_numeric_report_fields(
                [item["out_of_sample"] for item in windows]
            ),
        },
        "windows": windows,
    }


def _frame_period_summary(df: pd.DataFrame) -> dict[str, object]:
    return {
        "start_date": pd.Timestamp(df.index[0]).date().isoformat(),
        "end_date": pd.Timestamp(df.index[-1]).date().isoformat(),
        "bars_count": len(df),
    }


def _average_numeric_report_fields(
    reports: list[dict[str, object]],
) -> dict[str, object]:
    averages: dict[str, object] = {"windows_count": len(reports)}
    numeric_keys = sorted(
        {
            key
            for report in reports
            for key, value in report.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
    )
    for key in numeric_keys:
        values = [
            float(report[key])
            for report in reports
            if isinstance(report.get(key), (int, float))
            and not isinstance(report.get(key), bool)
        ]
        if values:
            averages[key] = round(sum(values) / len(values), 6)
    return averages


def _build_execution_payload(
    candidate_count: int,
    walk_forward_windows: int,
) -> dict[str, object]:
    estimated_total_runs = candidate_count * (1 + walk_forward_windows)
    async_recommended = estimated_total_runs >= LONG_TASK_RUN_THRESHOLD
    message = (
        f"当前 optimize 端点保持同步执行；预计触发 {estimated_total_runs} 次优化评估。"
    )
    if async_recommended:
        message += " 参数空间较大，建议后续接入异步任务队列或缩小搜索范围。"

    return {
        "mode": "sync",
        "async_supported": False,
        "async_recommended": async_recommended,
        "candidate_count": candidate_count,
        "walk_forward_windows": walk_forward_windows,
        "estimated_total_runs": estimated_total_runs,
        "long_task_threshold": LONG_TASK_RUN_THRESHOLD,
        "message": message,
    }


def _jsonable_value(value: object) -> object:
    """递归清理 numpy/pandas 标量与可迭代对象，确保可 JSON 序列化。"""
    if isinstance(value, dict):
        return {key: _jsonable_value(item) for key, item in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return [_jsonable_value(item) for item in value]

    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except (TypeError, ValueError):
            return value
    return value
