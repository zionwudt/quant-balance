"""策略定义 -- backtesting.py 风格 + vectorbt 信号函数。

backtesting.py 策略: 继承 Strategy，实现 init() / next()
vectorbt 信号函数: 普通函数，接收 DataFrame 返回 (entries, exits) 布尔 Series
"""

from __future__ import annotations

from collections.abc import Callable
from numbers import Number

import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover

from quant_balance.core.indicators import bollinger, ema, macd, rsi, sma


def _to_series(values: pd.Series | Number | object, index: pd.Index) -> pd.Series:
    """将输入统一转换为和目标索引对齐的 Series。"""
    if isinstance(values, pd.Series):
        return values.reindex(index)
    if isinstance(values, Number):
        return pd.Series(values, index=index)
    return pd.Series(values, index=index)


def _cross_above(
    left: pd.Series | Number | object,
    right: pd.Series | Number | object,
    *,
    index: pd.Index,
) -> pd.Series:
    left_series = _to_series(left, index)
    right_series = _to_series(right, index)
    result = (left_series > right_series) & (left_series.shift(1) <= right_series.shift(1))
    return result.fillna(False)


def _cross_below(
    left: pd.Series | Number | object,
    right: pd.Series | Number | object,
    *,
    index: pd.Index,
) -> pd.Series:
    left_series = _to_series(left, index)
    right_series = _to_series(right, index)
    result = (left_series < right_series) & (left_series.shift(1) >= right_series.shift(1))
    return result.fillna(False)


def _latest_cross_above(
    left: object,
    right: object,
) -> bool:
    values = _cross_above(left, right, index=pd.RangeIndex(len(left)))
    return bool(values.iloc[-1])


def _latest_cross_below(
    left: object,
    right: object,
) -> bool:
    values = _cross_below(left, right, index=pd.RangeIndex(len(left)))
    return bool(values.iloc[-1])


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


class MacdCross(Strategy):
    """MACD 零轴附近金叉/死叉趋势跟随策略。"""

    fast_period = 12
    slow_period = 26
    signal_period = 9

    def init(self):
        price = self.data.Close
        self.macd_line = self.I(
            lambda values: macd(values, self.fast_period, self.slow_period, self.signal_period)[0],
            price,
        )
        self.signal_line = self.I(
            lambda values: macd(values, self.fast_period, self.slow_period, self.signal_period)[1],
            price,
        )

    def next(self):
        if crossover(self.macd_line, self.signal_line):
            self.buy()
        elif crossover(self.signal_line, self.macd_line):
            self.position.close()


class RsiStrategy(Strategy):
    """RSI 超卖反弹策略。"""

    period = 14
    oversold = 30.0
    overbought = 70.0

    def init(self):
        self.rsi_value = self.I(rsi, self.data.Close, self.period)

    def next(self):
        if not self.position and _latest_cross_above(self.rsi_value, self.oversold):
            self.buy()
        elif self.position and _latest_cross_above(self.rsi_value, self.overbought):
            self.position.close()


class BollingerBreakout(Strategy):
    """布林带上轨突破入场、跌回中轨离场策略。"""

    period = 20
    num_std = 2.0

    def init(self):
        price = self.data.Close
        self.upper_band = self.I(
            lambda values: bollinger(values, self.period, self.num_std)[0],
            price,
        )
        self.middle_band = self.I(
            lambda values: bollinger(values, self.period, self.num_std)[1],
            price,
        )

    def next(self):
        if crossover(self.data.Close, self.upper_band):
            self.buy()
        elif crossover(self.middle_band, self.data.Close):
            self.position.close()


class GridStrategy(Strategy):
    """基于均线锚定上下网格的均值回归策略。"""

    anchor_period = 20
    grid_pct = 0.05

    def init(self):
        price = self.data.Close
        self.anchor = self.I(sma, price, self.anchor_period)

    def next(self):
        lower = self.anchor * (1 - self.grid_pct)
        upper = self.anchor * (1 + self.grid_pct)
        if not self.position and _latest_cross_below(self.data.Close, lower):
            self.buy()
        elif self.position and _latest_cross_above(self.data.Close, upper):
            self.position.close()


class DcaStrategy(Strategy):
    """定期定额买入策略。"""

    interval_days = 20
    trade_fraction = 0.2
    qb_exclusive_orders = False

    def init(self):
        self.bar_counter = 0

    def next(self):
        self.bar_counter += 1
        if self.trade_fraction <= 0 or self.trade_fraction > 1:
            raise ValueError("trade_fraction 必须位于 (0, 1] 区间")
        if self.interval_days < 1:
            raise ValueError("interval_days 必须 >= 1")
        if (self.bar_counter - 1) % self.interval_days == 0:
            self.buy(size=self.trade_fraction)


class MaRsiFilter(Strategy):
    """均线趋势 + RSI 动量过滤策略。"""

    fast_period = 10
    slow_period = 30
    rsi_period = 14
    rsi_threshold = 55.0
    exit_rsi = 45.0

    def init(self):
        price = self.data.Close
        self.fast_ma = self.I(sma, price, self.fast_period)
        self.slow_ma = self.I(sma, price, self.slow_period)
        self.rsi_value = self.I(rsi, price, self.rsi_period)

    def next(self):
        entry_state = (
            self.fast_ma[-1] > self.slow_ma[-1]
            and self.rsi_value[-1] > self.rsi_threshold
        )
        prev_entry_state = (
            self.fast_ma[-2] > self.slow_ma[-2]
            and self.rsi_value[-2] > self.rsi_threshold
        )
        exit_state = (
            self.fast_ma[-1] < self.slow_ma[-1]
            or self.rsi_value[-1] < self.exit_rsi
        )
        prev_exit_state = (
            self.fast_ma[-2] < self.slow_ma[-2]
            or self.rsi_value[-2] < self.exit_rsi
        )

        if not self.position and entry_state and not prev_entry_state:
            self.buy()
        elif self.position and exit_state and not prev_exit_state:
            self.position.close()


# ---------------------------------------------------------------------------
# vectorbt 信号函数（用于批量筛选）
# ---------------------------------------------------------------------------

def sma_cross_signals(
    df: pd.DataFrame,
    fast: int = 5,
    slow: int = 20,
) -> tuple[pd.Series, pd.Series]:
    """SMA 交叉信号 → (entries, exits)。"""
    fast_ma = sma(df["Close"], fast)
    slow_ma = sma(df["Close"], slow)
    entries = _cross_above(fast_ma, slow_ma, index=df.index)
    exits = _cross_below(fast_ma, slow_ma, index=df.index)
    return entries, exits


def ema_cross_signals(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
) -> tuple[pd.Series, pd.Series]:
    """EMA 交叉信号 → (entries, exits)。"""
    fast_ma = ema(df["Close"], fast)
    slow_ma = ema(df["Close"], slow)
    entries = _cross_above(fast_ma, slow_ma, index=df.index)
    exits = _cross_below(fast_ma, slow_ma, index=df.index)
    return entries, exits


def macd_signals(
    df: pd.DataFrame,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[pd.Series, pd.Series]:
    """MACD 金叉/死叉信号。"""
    macd_line, signal_line, _ = macd(df["Close"], fast_period, slow_period, signal_period)
    entries = _cross_above(macd_line, signal_line, index=df.index)
    exits = _cross_below(macd_line, signal_line, index=df.index)
    return entries, exits


def rsi_signals(
    df: pd.DataFrame,
    period: int = 14,
    oversold: float = 30.0,
    overbought: float = 70.0,
) -> tuple[pd.Series, pd.Series]:
    """RSI 超卖反弹 / 超买止盈信号。"""
    rsi_value = rsi(df["Close"], period)
    entries = _cross_above(rsi_value, oversold, index=df.index)
    exits = _cross_above(rsi_value, overbought, index=df.index)
    return entries, exits


def bollinger_signals(
    df: pd.DataFrame,
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[pd.Series, pd.Series]:
    """布林带上轨突破 / 中轨失守信号。"""
    upper_band, middle_band, _ = bollinger(df["Close"], period, num_std)
    entries = _cross_above(df["Close"], upper_band, index=df.index)
    exits = _cross_below(df["Close"], middle_band, index=df.index)
    return entries, exits


def grid_signals(
    df: pd.DataFrame,
    anchor_period: int = 20,
    grid_pct: float = 0.05,
) -> tuple[pd.Series, pd.Series]:
    """均线锚定网格的低吸 / 高抛信号。"""
    anchor = sma(df["Close"], anchor_period)
    lower = anchor * (1 - grid_pct)
    upper = anchor * (1 + grid_pct)
    entries = _cross_below(df["Close"], lower, index=df.index)
    exits = _cross_above(df["Close"], upper, index=df.index)
    return entries, exits


def dca_signals(
    df: pd.DataFrame,
    interval_days: int = 20,
    trade_fraction: float = 0.2,
) -> tuple[pd.Series, pd.Series]:
    """定投信号。

    entries 按固定间隔触发；配合筛选引擎的累积加仓参数使用。
    """
    if interval_days < 1:
        raise ValueError("interval_days 必须 >= 1")
    if trade_fraction <= 0 or trade_fraction > 1:
        raise ValueError("trade_fraction 必须位于 (0, 1] 区间")

    positions = pd.Series(range(len(df)), index=df.index)
    entries = (positions % interval_days == 0).fillna(False)
    exits = pd.Series(False, index=df.index)
    return entries.astype(bool), exits.astype(bool)


def ma_rsi_filter_signals(
    df: pd.DataFrame,
    fast_period: int = 10,
    slow_period: int = 30,
    rsi_period: int = 14,
    rsi_threshold: float = 55.0,
    exit_rsi: float = 45.0,
) -> tuple[pd.Series, pd.Series]:
    """均线趋势 + RSI 动量过滤信号。"""
    fast_ma = sma(df["Close"], fast_period)
    slow_ma = sma(df["Close"], slow_period)
    rsi_value = rsi(df["Close"], rsi_period)

    entry_state = ((fast_ma > slow_ma) & (rsi_value > rsi_threshold)).fillna(False)
    exit_state = ((fast_ma < slow_ma) | (rsi_value < exit_rsi)).fillna(False)

    entries = entry_state & ~entry_state.shift(1, fill_value=False)
    exits = exit_state & ~exit_state.shift(1, fill_value=False)
    return entries.fillna(False), exits.fillna(False)


def _dca_portfolio_kwargs(params: dict[str, object]) -> dict[str, object]:
    trade_fraction = float(params.get("trade_fraction", 0.2))
    return {
        "accumulate": True,
        "size": trade_fraction,
        "size_type": "percent",
    }


dca_signals.qb_portfolio_kwargs = _dca_portfolio_kwargs


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "sma_cross": SmaCross,
    "ema_cross": EmaCross,
    "buy_and_hold": BuyAndHold,
    "macd": MacdCross,
    "rsi": RsiStrategy,
    "bollinger": BollingerBreakout,
    "grid": GridStrategy,
    "dca": DcaStrategy,
    "ma_rsi_filter": MaRsiFilter,
}

SIGNAL_REGISTRY: dict[str, Callable] = {
    "sma_cross": sma_cross_signals,
    "ema_cross": ema_cross_signals,
    "macd": macd_signals,
    "rsi": rsi_signals,
    "bollinger": bollinger_signals,
    "grid": grid_signals,
    "dca": dca_signals,
    "ma_rsi_filter": ma_rsi_filter_signals,
}
