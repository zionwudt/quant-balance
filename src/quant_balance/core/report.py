"""回测报告 — 统一 backtesting.py 和 vectorbt 的统计输出。"""

from __future__ import annotations

from math import sqrt

import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def normalize_bt_stats(
    stats: pd.Series,
    risk_params: dict | None = None,
    *,
    benchmark_df: pd.DataFrame | None = None,
    benchmark_symbol: str | None = None,
    rolling_sharpe_window: int = 60,
) -> dict:
    """将 backtesting.py 的 stats Series 转为标准化字典。"""
    def _safe(key: str, default=None):
        try:
            val = stats[key]
            if isinstance(val, (pd.Series, pd.DataFrame)):
                return val
            if pd.isna(val):
                return default
            return val
        except (KeyError, TypeError):
            return default

    def _initial_equity(default=None):
        try:
            equity_curve = stats["_equity_curve"]
            if equity_curve is not None and not equity_curve.empty:
                return float(equity_curve.iloc[0]["Equity"])
        except (KeyError, TypeError, ValueError):
            pass
        return default

    equity_curve = _safe("_equity_curve")

    report = {
        "initial_equity": _initial_equity(),
        "final_equity": _safe("Equity Final [$]"),
        "total_return_pct": _safe("Return [%]"),
        "annualized_return_pct": _safe("Return (Ann.) [%]"),
        "sharpe_ratio": _safe("Sharpe Ratio"),
        "sortino_ratio": _safe("Sortino Ratio"),
        "max_drawdown_pct": abs(_safe("Max. Drawdown [%]", 0.0)),
        "calmar_ratio": None,
        "trades_count": _safe("# Trades", 0),
        "win_rate_pct": _safe("Win Rate [%]"),
        "best_trade_pct": _safe("Best Trade [%]"),
        "worst_trade_pct": _safe("Worst Trade [%]"),
        "avg_trade_pct": _safe("Avg. Trade [%]"),
        "profit_factor": _safe("Profit Factor"),
        "expectancy_pct": _safe("Expectancy [%]"),
        "avg_trade_duration": str(_safe("Avg. Trade Duration", "")),
        "exposure_pct": _safe("Exposure Time [%]"),
        "monthly_returns": [],
        "rolling_sharpe_window_bars": rolling_sharpe_window,
        "rolling_sharpe": [],
        "yearly_stats": [],
    }
    report["calmar_ratio"] = _rounded(_calmar_ratio(
        report.get("annualized_return_pct"),
        report.get("max_drawdown_pct"),
    ))
    equity_series = _equity_series(equity_curve)
    report["monthly_returns"] = _monthly_return_table(equity_series)
    report["rolling_sharpe"] = _rolling_sharpe_series(
        equity_series,
        window=rolling_sharpe_window,
    )
    report["yearly_stats"] = _yearly_stats(equity_series)
    if benchmark_df is not None:
        report.update(
            _benchmark_summary(
                equity_series,
                benchmark_df,
                benchmark_symbol=benchmark_symbol,
            )
        )
    report.update(_risk_summary(_safe("_trades"), risk_params))
    return report


def normalize_vbt_stats(
    stats: pd.Series,
    equity_series: pd.Series | pd.DataFrame | None = None,
    *,
    initial_equity: float | None = None,
    rolling_sharpe_window: int = 60,
) -> dict:
    """将 vectorbt 的 pf.stats() 转为标准化字典。"""
    def _safe(key: str, default=None):
        try:
            val = stats[key]
            if pd.isna(val):
                return default
            return val
        except (KeyError, TypeError):
            return default

    normalized_equity = _normalize_equity_series(equity_series)
    resolved_initial_equity = initial_equity
    if resolved_initial_equity is None and normalized_equity is not None and not normalized_equity.empty:
        resolved_initial_equity = float(normalized_equity.iloc[0])

    max_drawdown_pct = _safe("Max Drawdown [%]")
    if max_drawdown_pct is not None:
        max_drawdown_pct = abs(max_drawdown_pct)

    report = {
        "initial_equity": _rounded(resolved_initial_equity),
        "annualized_return_pct": _rounded(_annualized_return_pct(normalized_equity)),
        "total_return_pct": _safe("Total Return [%]"),
        "sharpe_ratio": _safe("Sharpe Ratio"),
        "max_drawdown_pct": _rounded(max_drawdown_pct),
        "total_trades": _safe("Total Trades", 0),
        "win_rate_pct": _safe("Win Rate [%]"),
        "profit_factor": _safe("Profit Factor"),
        "expectancy": _safe("Expectancy"),
        "final_value": _rounded(
            float(normalized_equity.iloc[-1])
            if normalized_equity is not None and not normalized_equity.empty
            else _safe("End Value")
        ),
        "final_equity": _rounded(
            float(normalized_equity.iloc[-1])
            if normalized_equity is not None and not normalized_equity.empty
            else _safe("End Value")
        ),
        "calmar_ratio": None,
        "monthly_returns": [],
        "rolling_sharpe_window_bars": rolling_sharpe_window,
        "rolling_sharpe": [],
        "yearly_stats": [],
    }
    report["calmar_ratio"] = _rounded(_calmar_ratio(
        report.get("annualized_return_pct"),
        report.get("max_drawdown_pct"),
    ))
    report["monthly_returns"] = _monthly_return_table(normalized_equity)
    report["rolling_sharpe"] = _rolling_sharpe_series(
        normalized_equity,
        window=rolling_sharpe_window,
    )
    report["yearly_stats"] = _yearly_stats(normalized_equity)
    return report


def build_equity_performance_report(
    equity_series: pd.Series | pd.DataFrame | None,
    *,
    closed_trade_pnls: list[float] | None = None,
    closed_trade_returns_pct: list[float] | None = None,
    orders_count: int | None = None,
    exposure_pct: float | None = None,
    rolling_sharpe_window: int = 60,
) -> dict[str, object]:
    """基于任意权益曲线构建与回测结果风格一致的绩效摘要。"""

    normalized_equity = _normalize_equity_series(equity_series)
    returns = (
        normalized_equity.pct_change().dropna()
        if normalized_equity is not None and len(normalized_equity) > 1
        else None
    )
    realized_pnls = [float(value) for value in (closed_trade_pnls or [])]
    realized_returns = [float(value) for value in (closed_trade_returns_pct or [])]

    initial_equity = None
    final_equity = None
    total_return_pct = None
    if normalized_equity is not None and not normalized_equity.empty:
        initial_equity = float(normalized_equity.iloc[0])
        final_equity = float(normalized_equity.iloc[-1])
        if initial_equity > 0:
            total_return_pct = _rounded((final_equity / initial_equity - 1) * 100)

    wins = [value for value in realized_pnls if value > 0]
    losses = [abs(value) for value in realized_pnls if value < 0]
    closed_trades_count = len(realized_pnls)
    avg_trade_pct = (
        _rounded(sum(realized_returns) / len(realized_returns))
        if realized_returns
        else None
    )

    annualized_return_pct = _rounded(_annualized_return_pct(normalized_equity))
    max_drawdown_pct = _rounded(_max_drawdown_pct(normalized_equity))
    report = {
        "initial_equity": _rounded(initial_equity),
        "final_equity": _rounded(final_equity),
        "final_value": _rounded(final_equity),
        "total_return_pct": total_return_pct,
        "annualized_return_pct": annualized_return_pct,
        "sharpe_ratio": _rounded(_annualized_sharpe(returns)),
        "sortino_ratio": _rounded(_annualized_sortino(returns)),
        "max_drawdown_pct": max_drawdown_pct,
        "calmar_ratio": _rounded(_calmar_ratio(annualized_return_pct, max_drawdown_pct)),
        "trades_count": closed_trades_count,
        "orders_count": int(orders_count if orders_count is not None else closed_trades_count),
        "win_rate_pct": _rounded(len(wins) / closed_trades_count * 100) if closed_trades_count else None,
        "best_trade_pct": _rounded(max(realized_returns)) if realized_returns else None,
        "worst_trade_pct": _rounded(min(realized_returns)) if realized_returns else None,
        "avg_trade_pct": avg_trade_pct,
        "profit_factor": _rounded(sum(wins) / sum(losses)) if wins and losses else None,
        "expectancy_pct": avg_trade_pct,
        "avg_trade_duration": None,
        "exposure_pct": _rounded(exposure_pct),
        "monthly_returns": _monthly_return_table(normalized_equity),
        "rolling_sharpe_window_bars": rolling_sharpe_window,
        "rolling_sharpe": _rolling_sharpe_series(
            normalized_equity,
            window=rolling_sharpe_window,
        ),
        "yearly_stats": _yearly_stats(normalized_equity),
    }
    return report


def bt_trades_to_dicts(
    trades_df: pd.DataFrame,
    risk_params: dict | None = None,
) -> list[dict]:
    """将 backtesting.py 的交易 DataFrame 转为字典列表。"""
    if trades_df is None or trades_df.empty:
        return []
    records = []
    for _, row in trades_df.iterrows():
        stop_loss_price, take_profit_price = _trade_risk_targets(row, risk_params)
        records.append({
            "size": int(row.get("Size", 0)),
            "entry_bar": int(row.get("EntryBar", 0)),
            "exit_bar": int(row.get("ExitBar", 0)),
            "entry_price": float(row.get("EntryPrice", 0)),
            "exit_price": float(row.get("ExitPrice", 0)),
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
            "pnl": float(row.get("PnL", 0)),
            "return_pct": float(row.get("ReturnPct", 0)) * 100,
            "entry_time": str(row.get("EntryTime", "")),
            "exit_time": str(row.get("ExitTime", "")),
            "duration": str(row.get("Duration", "")),
            "exit_reason": _infer_exit_reason(row, risk_params),
        })
    return records


def equity_curve_to_dicts(
    equity_df: pd.DataFrame,
    benchmark_df: pd.DataFrame | None = None,
) -> list[dict]:
    """将 backtesting.py 的权益曲线 DataFrame 转为字典列表。"""
    if equity_df is None or equity_df.empty:
        return []

    benchmark_curve = _build_benchmark_equity_curve(_equity_series(equity_df), benchmark_df)
    initial_equity = float(equity_df.iloc[0]["Equity"])
    records = []
    for idx, row in equity_df.iterrows():
        record = {
            "date": str(idx),
            "equity": float(row.get("Equity", 0)),
        }
        if benchmark_curve is not None:
            benchmark_equity = _rounded(benchmark_curve.loc[pd.Timestamp(idx)])
            strategy_return_pct = _rounded((record["equity"] / initial_equity - 1) * 100)
            benchmark_return_pct = _rounded((benchmark_equity / initial_equity - 1) * 100)
            record.update({
                "benchmark_equity": benchmark_equity,
                "strategy_return_pct": strategy_return_pct,
                "benchmark_return_pct": benchmark_return_pct,
                "excess_return_pct": _rounded(strategy_return_pct - benchmark_return_pct),
            })
        records.append(record)
    return records


def _risk_summary(
    trades_df: pd.DataFrame | None,
    risk_params: dict | None,
) -> dict[str, object]:
    stop_loss_pct = _optional_float((risk_params or {}).get("stop_loss_pct"))
    take_profit_pct = _optional_float((risk_params or {}).get("take_profit_pct"))
    if stop_loss_pct is None and take_profit_pct is None:
        return {}

    trades = bt_trades_to_dicts(trades_df, risk_params)
    return {
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "stop_loss_trades": sum(trade["exit_reason"] == "stop_loss" for trade in trades),
        "take_profit_trades": sum(trade["exit_reason"] == "take_profit" for trade in trades),
    }


def _trade_risk_targets(
    row: pd.Series,
    risk_params: dict | None,
) -> tuple[float | None, float | None]:
    entry_price = float(row.get("EntryPrice", 0))
    stop_loss_pct = _optional_float((risk_params or {}).get("stop_loss_pct"))
    take_profit_pct = _optional_float((risk_params or {}).get("take_profit_pct"))

    stop_loss_price = _safe_trade_float(row.get("SL"))
    take_profit_price = _safe_trade_float(row.get("TP"))

    if stop_loss_price is None and stop_loss_pct is not None:
        stop_loss_price = entry_price * (1 - stop_loss_pct)
    if take_profit_price is None and take_profit_pct is not None:
        take_profit_price = entry_price * (1 + take_profit_pct)
    return stop_loss_price, take_profit_price


def _infer_exit_reason(
    row: pd.Series,
    risk_params: dict | None,
) -> str | None:
    entry_price = float(row.get("EntryPrice", 0))
    exit_price = float(row.get("ExitPrice", 0))
    stop_loss_pct = _optional_float((risk_params or {}).get("stop_loss_pct"))
    take_profit_pct = _optional_float((risk_params or {}).get("take_profit_pct"))
    tolerance = max(entry_price * 1e-6, 1e-9)

    if stop_loss_pct is not None:
        stop_threshold = entry_price * (1 - stop_loss_pct)
        if exit_price <= stop_threshold + tolerance:
            return "stop_loss"
    if take_profit_pct is not None:
        take_profit_threshold = entry_price * (1 + take_profit_pct)
        if exit_price >= take_profit_threshold - tolerance:
            return "take_profit"
    return None


def _optional_float(value: object) -> float | None:
    if value in (None, "", 0, 0.0):
        return None
    return float(value)


def _safe_trade_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _rounded(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), 6)


def _equity_series(equity_df: pd.DataFrame | None) -> pd.Series | None:
    if equity_df is None or equity_df.empty or "Equity" not in equity_df:
        return None
    series = equity_df["Equity"].astype(float).copy()
    series.index = pd.to_datetime(series.index)
    return series.sort_index()


def _normalize_equity_series(equity_series: pd.Series | pd.DataFrame | None) -> pd.Series | None:
    if equity_series is None:
        return None
    if isinstance(equity_series, pd.DataFrame):
        if equity_series.empty:
            return None
        if "Equity" in equity_series:
            series = equity_series["Equity"]
        elif equity_series.shape[1] == 1:
            series = equity_series.iloc[:, 0]
        else:
            return None
    else:
        series = equity_series

    if series is None or len(series) == 0:
        return None
    normalized = series.astype(float).copy()
    normalized.index = pd.to_datetime(normalized.index)
    return normalized.sort_index()


def _monthly_return_table(equity_series: pd.Series | None) -> list[dict[str, object]]:
    if equity_series is None or equity_series.empty:
        return []
    month_end = equity_series.resample("ME").last()
    previous = month_end.shift(1)
    previous.iloc[0] = equity_series.iloc[0]
    returns = (month_end / previous - 1) * 100
    return [
        {"month": idx.strftime("%Y-%m"), "return_pct": _rounded(value)}
        for idx, value in returns.items()
        if not pd.isna(value)
    ]


def _rolling_sharpe_series(
    equity_series: pd.Series | None,
    *,
    window: int,
) -> list[dict[str, object]]:
    if equity_series is None or equity_series.empty or window < 2:
        return []
    returns = equity_series.pct_change().dropna()
    if len(returns) < window:
        return []
    rolling = returns.rolling(window).apply(_rolling_sharpe_value, raw=False).dropna()
    return [
        {"date": idx.date().isoformat(), "sharpe_ratio": _rounded(value)}
        for idx, value in rolling.items()
        if not pd.isna(value)
    ]


def _rolling_sharpe_value(returns: pd.Series) -> float:
    sharpe_ratio = _annualized_sharpe(returns)
    if sharpe_ratio is None:
        return float("nan")
    return sharpe_ratio


def _yearly_stats(equity_series: pd.Series | None) -> list[dict[str, object]]:
    if equity_series is None or equity_series.empty:
        return []
    records: list[dict[str, object]] = []
    for year, series in equity_series.groupby(equity_series.index.year):
        initial_equity = float(series.iloc[0])
        final_equity = float(series.iloc[-1])
        total_return_pct = None
        if initial_equity > 0:
            total_return_pct = _rounded((final_equity / initial_equity - 1) * 100)
        records.append({
            "year": int(year),
            "initial_equity": initial_equity,
            "final_equity": final_equity,
            "total_return_pct": total_return_pct,
            "annualized_return_pct": _rounded(_annualized_return_pct(series)),
            "max_drawdown_pct": _rounded(_max_drawdown_pct(series)),
        })
    return records


def _benchmark_summary(
    equity_series: pd.Series | None,
    benchmark_df: pd.DataFrame,
    *,
    benchmark_symbol: str | None = None,
) -> dict[str, object]:
    benchmark_curve = _build_benchmark_equity_curve(equity_series, benchmark_df)
    if equity_series is None or benchmark_curve is None:
        return {}

    strategy_total_return_pct = _rounded((equity_series.iloc[-1] / equity_series.iloc[0] - 1) * 100)
    benchmark_total_return_pct = _rounded((benchmark_curve.iloc[-1] / benchmark_curve.iloc[0] - 1) * 100)
    strategy_returns = equity_series.pct_change().dropna()
    benchmark_returns = benchmark_curve.pct_change().dropna()
    beta, alpha_annualized_pct = _beta_alpha(strategy_returns, benchmark_returns)
    benchmark_annualized_return_pct = _rounded(_annualized_return_pct(benchmark_curve))
    benchmark_max_drawdown_pct = _rounded(_max_drawdown_pct(benchmark_curve))

    return {
        "benchmark_symbol": benchmark_symbol,
        "benchmark_final_equity": _rounded(benchmark_curve.iloc[-1]),
        "benchmark_total_return_pct": benchmark_total_return_pct,
        "benchmark_annualized_return_pct": benchmark_annualized_return_pct,
        "benchmark_sharpe_ratio": _rounded(_annualized_sharpe(benchmark_returns)),
        "benchmark_max_drawdown_pct": benchmark_max_drawdown_pct,
        "benchmark_calmar_ratio": _rounded(_calmar_ratio(
            benchmark_annualized_return_pct,
            benchmark_max_drawdown_pct,
        )),
        "excess_return_pct": _rounded(strategy_total_return_pct - benchmark_total_return_pct),
        "beta": _rounded(beta),
        "alpha_annualized_pct": _rounded(alpha_annualized_pct),
    }


def _build_benchmark_equity_curve(
    equity_series: pd.Series | None,
    benchmark_df: pd.DataFrame | None,
) -> pd.Series | None:
    if equity_series is None or benchmark_df is None or benchmark_df.empty or "Close" not in benchmark_df:
        return None

    benchmark_close = benchmark_df["Close"].astype(float).copy()
    benchmark_close.index = pd.to_datetime(benchmark_close.index)
    benchmark_close = benchmark_close.sort_index().reindex(equity_series.index).ffill()
    if benchmark_close.empty or benchmark_close.isna().any():
        return None

    initial_equity = float(equity_series.iloc[0])
    initial_close = float(benchmark_close.iloc[0])
    if initial_close <= 0:
        return None
    return initial_equity * benchmark_close / initial_close


def _annualized_return_pct(equity_series: pd.Series | None) -> float | None:
    if equity_series is None or len(equity_series) < 2:
        return None
    initial_value = float(equity_series.iloc[0])
    final_value = float(equity_series.iloc[-1])
    if initial_value <= 0 or final_value <= 0:
        return None
    periods = len(equity_series) - 1
    if periods <= 0:
        return None
    return ((final_value / initial_value) ** (TRADING_DAYS_PER_YEAR / periods) - 1) * 100


def _max_drawdown_pct(equity_series: pd.Series | None) -> float | None:
    if equity_series is None or equity_series.empty:
        return None
    drawdown = equity_series / equity_series.cummax() - 1
    return abs(float(drawdown.min())) * 100


def _annualized_sharpe(returns: pd.Series | None) -> float | None:
    if returns is None or returns.empty:
        return None
    volatility = float(returns.std(ddof=0))
    if volatility <= 0 or pd.isna(volatility):
        return None
    return float(returns.mean()) / volatility * sqrt(TRADING_DAYS_PER_YEAR)


def _annualized_sortino(returns: pd.Series | None) -> float | None:
    if returns is None or returns.empty:
        return None
    downside = returns[returns < 0]
    if downside.empty:
        return None
    downside_volatility = float(downside.std(ddof=0))
    if downside_volatility <= 0 or pd.isna(downside_volatility):
        return None
    return float(returns.mean()) / downside_volatility * sqrt(TRADING_DAYS_PER_YEAR)


def _calmar_ratio(
    annualized_return_pct: object,
    max_drawdown_pct: object,
) -> float | None:
    if annualized_return_pct in (None, "") or max_drawdown_pct in (None, "", 0, 0.0):
        return None
    return float(annualized_return_pct) / float(max_drawdown_pct)


def _beta_alpha(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> tuple[float | None, float | None]:
    pair = pd.concat(
        {"strategy": strategy_returns, "benchmark": benchmark_returns},
        axis=1,
    ).dropna()
    if pair.empty:
        return None, None

    benchmark_var = float(pair["benchmark"].var(ddof=0))
    if benchmark_var <= 0 or pd.isna(benchmark_var):
        return None, None

    centered_strategy = pair["strategy"] - pair["strategy"].mean()
    centered_benchmark = pair["benchmark"] - pair["benchmark"].mean()
    beta = float((centered_strategy * centered_benchmark).mean() / benchmark_var)
    alpha_daily = float(pair["strategy"].mean() - beta * pair["benchmark"].mean())
    return beta, alpha_daily * TRADING_DAYS_PER_YEAR * 100
