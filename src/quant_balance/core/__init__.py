"""回测核心子包。"""

from quant_balance.core.backtest import BacktestResult, optimize, run_backtest
from quant_balance.core.report import (
    bt_trades_to_dicts,
    equity_curve_to_dicts,
    normalize_bt_stats,
    normalize_vbt_stats,
)
from quant_balance.core.screening import ScreeningResult, run_screening
from quant_balance.core.strategies import (
    BuyAndHold,
    EmaCross,
    SIGNAL_REGISTRY,
    STRATEGY_REGISTRY,
    SmaCross,
    ema_cross_signals,
    sma_cross_signals,
)

__all__ = [
    "BacktestResult",
    "BuyAndHold",
    "EmaCross",
    "SIGNAL_REGISTRY",
    "STRATEGY_REGISTRY",
    "ScreeningResult",
    "SmaCross",
    "bt_trades_to_dicts",
    "ema_cross_signals",
    "equity_curve_to_dicts",
    "normalize_bt_stats",
    "normalize_vbt_stats",
    "optimize",
    "run_backtest",
    "run_screening",
    "sma_cross_signals",
]
