"""API 元信息。"""

from __future__ import annotations

from quant_balance.core.factors import list_factor_definitions
from quant_balance.core.strategies import SIGNAL_REGISTRY, STRATEGY_REGISTRY


def build_api_meta() -> dict:
    """返回 API 元信息，包含可用策略和注意事项。"""
    return {
        "strategies": list(STRATEGY_REGISTRY.keys()),
        "signals": list(SIGNAL_REGISTRY.keys()),
        "factors": list_factor_definitions(),
        "defaults": {
            "backtest": {
                "asset_type": "stock",
                "strategy": "sma_cross",
                "cash": 100_000.0,
                "commission": 0.001,
                "slippage_mode": "off",
                "slippage_rate": 0.0,
                "benchmark_symbol": None,
                "benchmark_asset_type": None,
                "data_provider": None,
                "benchmark_data_provider": None,
            },
            "optimize": {
                "asset_type": "stock",
                "strategy": "sma_cross",
                "cash": 100_000.0,
                "commission": 0.001,
                "maximize": "Sharpe Ratio",
                "data_provider": None,
            },
            "screening": {
                "asset_type": "stock",
                "signal": "sma_cross",
                "pool_filters": {
                    "industries": [],
                    "exclude_st": False,
                    "min_listing_days": None,
                    "min_market_cap": None,
                    "max_market_cap": None,
                    "min_pe": None,
                    "max_pe": None,
                },
                "top_n": 20,
                "cash": 100_000.0,
                "data_provider": None,
            },
            "stock_pool": {
                "filters": {
                    "industries": [],
                    "exclude_st": False,
                    "min_listing_days": None,
                    "min_market_cap": None,
                    "max_market_cap": None,
                    "min_pe": None,
                    "max_pe": None,
                },
            },
            "factors_rank": {
                "factors": [
                    {"name": "roe", "weight": 0.4},
                    {"name": "pe", "weight": 0.25},
                    {"name": "pb", "weight": 0.2},
                    {"name": "dv_ratio", "weight": 0.15},
                ],
                "pool_filters": {
                    "industries": [],
                    "exclude_st": False,
                    "min_listing_days": None,
                    "min_market_cap": None,
                    "max_market_cap": None,
                    "min_pe": None,
                    "max_pe": None,
                },
                "top_n": 50,
            },
            "portfolio": {
                "allocation": "equal",
                "rebalance_frequency": "monthly",
                "cash": 100_000.0,
                "commission": 0.001,
                "data_provider": None,
            },
            "scheduler": {
                "enabled": False,
                "scan_time": "16:00",
                "strategies": ["macd", "rsi"],
                "symbols_source": "stock_pool",
                "asset_type": "stock",
                "top_n": 20,
                "lookback_days": 365,
                "cash": 100_000.0,
                "data_provider": None,
            },
        },
        "notes": [
            "回测引擎基于 backtesting.py，支持精细化单股回测和参数优化。",
            "批量筛选引擎基于 vectorbt，支持向量化快速扫描多只股票。",
            "历史股票池支持行业、市值、PE、ST、次新等前置过滤，并继续以 get_pool_at_date() 为底座。",
            "多因子打分引擎支持因子标准化、加权总分与排名，可直接用于筛选研究与组合候选池构建。",
            "组合回测基于 vectorbt 目标权重矩阵，适合做多标的轮动与再平衡研究。",
            "scheduler.enabled=true 时，服务启动后会自动恢复盘后扫描调度；也可通过 API 手动触发。",
            "数据默认使用前复权价格（qfq）。",
            "行情数据默认按 akshare -> baostock -> tushare 顺序回退，也可在请求中显式指定。",
            "backtest / optimize / screening 支持 asset_type=convertible_bond；当前可转债仅支持 tushare，并沿用简化版股票化撮合规则。",
            "默认面向本地研究演示，不作为实盘建议。",
        ],
        "server_mode": "api",
    }
