"""API 元信息。"""

from __future__ import annotations

from quant_balance.core.strategies import SIGNAL_REGISTRY, STRATEGY_REGISTRY


def build_api_meta() -> dict:
    """返回 API 元信息，包含可用策略和注意事项。"""
    return {
        "strategies": list(STRATEGY_REGISTRY.keys()),
        "signals": list(SIGNAL_REGISTRY.keys()),
        "defaults": {
            "backtest": {
                "strategy": "sma_cross",
                "cash": 100_000.0,
                "commission": 0.001,
                "data_provider": None,
            },
            "optimize": {
                "strategy": "sma_cross",
                "cash": 100_000.0,
                "commission": 0.001,
                "maximize": "Sharpe Ratio",
                "data_provider": None,
            },
            "screening": {
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
            "portfolio": {
                "allocation": "equal",
                "rebalance_frequency": "monthly",
                "cash": 100_000.0,
                "commission": 0.001,
                "data_provider": None,
            },
        },
        "notes": [
            "回测引擎基于 backtesting.py，支持精细化单股回测和参数优化。",
            "批量筛选引擎基于 vectorbt，支持向量化快速扫描多只股票。",
            "历史股票池支持行业、市值、PE、ST、次新等前置过滤，并继续以 get_pool_at_date() 为底座。",
            "组合回测基于 vectorbt 目标权重矩阵，适合做多标的轮动与再平衡研究。",
            "数据默认使用前复权价格（qfq）。",
            "行情数据默认按 akshare -> baostock -> tushare 顺序回退，也可在请求中显式指定。",
            "默认面向本地研究演示，不作为实盘建议。",
        ],
        "server_mode": "api",
    }
