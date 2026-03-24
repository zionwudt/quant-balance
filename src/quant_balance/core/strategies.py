"""策略定义 -- backtesting.py 风格 + vectorbt 信号函数。

backtesting.py 策略: 继承 Strategy，实现 init() / next()
vectorbt 信号函数: 普通函数，接收 DataFrame 返回 (entries, exits) 布尔 Series
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover

from quant_balance.core.indicators import ema, sma


# ---------------------------------------------------------------------------
# backtesting.py 策略类
# ---------------------------------------------------------------------------

class SmaCross(Strategy):
    """SMA 金叉/死叉策略。"""

    fast_period = 5
    slow_period = 20

    def init(self):
        price = self.data.Close
        self.fast_ma = self.I(sma, price, self.fast_period)
        self.slow_ma = self.I(sma, price, self.slow_period)

    def next(self):
        if crossover(self.fast_ma, self.slow_ma):
            self.buy()
        elif crossover(self.slow_ma, self.fast_ma):
            self.position.close()


class EmaCross(Strategy):
    """EMA 金叉/死叉策略。"""

    fast_period = 12
    slow_period = 26

    def init(self):
        price = self.data.Close
        self.fast_ma = self.I(ema, price, self.fast_period)
        self.slow_ma = self.I(ema, price, self.slow_period)

    def next(self):
        if crossover(self.fast_ma, self.slow_ma):
            self.buy()
        elif crossover(self.slow_ma, self.fast_ma):
            self.position.close()


class BuyAndHold(Strategy):
    """买入并持有。"""

    def init(self):
        pass

    def next(self):
        if not self.position:
            self.buy()


# ---------------------------------------------------------------------------
# vectorbt 信号函数（用于批量筛选）
# ---------------------------------------------------------------------------

def sma_cross_signals(
    df: pd.DataFrame, fast: int = 5, slow: int = 20,
) -> tuple[pd.Series, pd.Series]:
    """SMA 交叉信号 → (entries, exits)。"""
    fast_ma = sma(df["Close"], fast)
    slow_ma = sma(df["Close"], slow)
    entries = (fast_ma > slow_ma) & (fast_ma.shift(1) <= slow_ma.shift(1))
    exits = (fast_ma < slow_ma) & (fast_ma.shift(1) >= slow_ma.shift(1))
    return entries.fillna(False), exits.fillna(False)


def ema_cross_signals(
    df: pd.DataFrame, fast: int = 12, slow: int = 26,
) -> tuple[pd.Series, pd.Series]:
    """EMA 交叉信号 → (entries, exits)。"""
    fast_ma = ema(df["Close"], fast)
    slow_ma = ema(df["Close"], slow)
    entries = (fast_ma > slow_ma) & (fast_ma.shift(1) <= slow_ma.shift(1))
    exits = (fast_ma < slow_ma) & (fast_ma.shift(1) >= slow_ma.shift(1))
    return entries.fillna(False), exits.fillna(False)


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "sma_cross": SmaCross,
    "ema_cross": EmaCross,
    "buy_and_hold": BuyAndHold,
}

SIGNAL_REGISTRY: dict[str, Callable] = {
    "sma_cross": sma_cross_signals,
    "ema_cross": ema_cross_signals,
}
