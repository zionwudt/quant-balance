"""技术指标库 — 纯 pandas 实现，不依赖 ta-lib。

所有函数接收 pandas.Series，返回 pandas.Series。
窗口不足的位置返回 NaN，空输入返回空 Series。
"""

from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    """简单移动平均线。"""
    return pd.Series(series).rolling(period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """指数移动平均线。"""
    return pd.Series(series).ewm(span=period, adjust=False).mean()


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD 指标。

    Returns:
        (dif, dea, histogram)
        - dif: 快线 EMA - 慢线 EMA
        - dea: dif 的信号线 EMA
        - histogram: dif - dea (柱状图，部分文献乘以2)
    """
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    dif = fast_ema - slow_ema
    dea = ema(dif, signal)
    hist = dif - dea
    return dif, dea, hist


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI 相对强弱指数 (Wilder 平滑)。"""
    s = pd.Series(series)
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def bollinger(
    series: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """布林带。

    Returns:
        (upper, middle, lower)
    """
    middle = sma(series, period)
    std = pd.Series(series).rolling(period).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper, middle, lower


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """ATR 平均真实波幅。"""
    h = pd.Series(high)
    l = pd.Series(low)
    c = pd.Series(close)
    prev_close = c.shift(1)
    tr = pd.concat([
        h - l,
        (h - prev_close).abs(),
        (l - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def kdj(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 9,
    d_period: int = 3,
    j_smooth: int = 3,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """KDJ 随机指标。

    Returns:
        (K, D, J)
    """
    h = pd.Series(high)
    l = pd.Series(low)
    c = pd.Series(close)
    lowest = l.rolling(k_period).min()
    highest = h.rolling(k_period).max()
    rsv = (c - lowest) / (highest - lowest) * 100
    k = rsv.ewm(com=d_period - 1, min_periods=d_period, adjust=False).mean()
    d = k.ewm(com=j_smooth - 1, min_periods=j_smooth, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j


def volume_ma(volume: pd.Series, period: int = 20) -> pd.Series:
    """成交量移动平均线。"""
    return sma(volume, period)
