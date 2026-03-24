"""回测报告 — 统一 backtesting.py 和 vectorbt 的统计输出。"""

from __future__ import annotations

import pandas as pd


def normalize_bt_stats(stats: pd.Series) -> dict:
    """将 backtesting.py 的 stats Series 转为标准化字典。"""
    def _safe(key: str, default=None):
        try:
            val = stats[key]
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

    return {
        "initial_equity": _initial_equity(),
        "final_equity": _safe("Equity Final [$]"),
        "total_return_pct": _safe("Return [%]"),
        "annualized_return_pct": _safe("Return (Ann.) [%]"),
        "sharpe_ratio": _safe("Sharpe Ratio"),
        "sortino_ratio": _safe("Sortino Ratio"),
        "max_drawdown_pct": abs(_safe("Max. Drawdown [%]", 0.0)),
        "trades_count": _safe("# Trades", 0),
        "win_rate_pct": _safe("Win Rate [%]"),
        "best_trade_pct": _safe("Best Trade [%]"),
        "worst_trade_pct": _safe("Worst Trade [%]"),
        "avg_trade_pct": _safe("Avg. Trade [%]"),
        "profit_factor": _safe("Profit Factor"),
        "expectancy_pct": _safe("Expectancy [%]"),
        "avg_trade_duration": str(_safe("Avg. Trade Duration", "")),
        "exposure_pct": _safe("Exposure Time [%]"),
    }


def normalize_vbt_stats(stats: pd.Series) -> dict:
    """将 vectorbt 的 pf.stats() 转为标准化字典。"""
    def _safe(key: str, default=None):
        try:
            val = stats[key]
            if pd.isna(val):
                return default
            return val
        except (KeyError, TypeError):
            return default

    return {
        "total_return_pct": _safe("Total Return [%]"),
        "sharpe_ratio": _safe("Sharpe Ratio"),
        "max_drawdown_pct": _safe("Max Drawdown [%]"),
        "total_trades": _safe("Total Trades", 0),
        "win_rate_pct": _safe("Win Rate [%]"),
        "profit_factor": _safe("Profit Factor"),
        "expectancy": _safe("Expectancy"),
        "final_value": _safe("End Value"),
    }


def bt_trades_to_dicts(trades_df: pd.DataFrame) -> list[dict]:
    """将 backtesting.py 的交易 DataFrame 转为字典列表。"""
    if trades_df is None or trades_df.empty:
        return []
    records = []
    for _, row in trades_df.iterrows():
        records.append({
            "size": int(row.get("Size", 0)),
            "entry_bar": int(row.get("EntryBar", 0)),
            "exit_bar": int(row.get("ExitBar", 0)),
            "entry_price": float(row.get("EntryPrice", 0)),
            "exit_price": float(row.get("ExitPrice", 0)),
            "pnl": float(row.get("PnL", 0)),
            "return_pct": float(row.get("ReturnPct", 0)) * 100,
            "entry_time": str(row.get("EntryTime", "")),
            "exit_time": str(row.get("ExitTime", "")),
            "duration": str(row.get("Duration", "")),
        })
    return records


def equity_curve_to_dicts(equity_df: pd.DataFrame) -> list[dict]:
    """将 backtesting.py 的权益曲线 DataFrame 转为字典列表。"""
    if equity_df is None or equity_df.empty:
        return []
    records = []
    for idx, row in equity_df.iterrows():
        records.append({
            "date": str(idx),
            "equity": float(row.get("Equity", 0)),
        })
    return records
