"""技术指标库单元测试。"""

import numpy as np
import pandas as pd
import pytest

from quant_balance.core.indicators import (
    atr,
    bollinger,
    ema,
    kdj,
    macd,
    rsi,
    sma,
    volume_ma,
)


@pytest.fixture
def prices():
    """生成一段上涨-下跌的模拟价格序列。"""
    np.random.seed(42)
    n = 100
    trend = np.concatenate([np.linspace(10, 20, n // 2), np.linspace(20, 12, n // 2)])
    noise = np.random.normal(0, 0.3, n)
    return pd.Series(trend + noise, name="Close")


@pytest.fixture
def ohlcv(prices):
    """从价格序列生成 OHLCV 数据。"""
    np.random.seed(42)
    high = prices + np.abs(np.random.normal(0, 0.5, len(prices)))
    low = prices - np.abs(np.random.normal(0, 0.5, len(prices)))
    volume = pd.Series(np.random.randint(1000, 10000, len(prices)), dtype=float)
    return high, low, prices, volume


# ── SMA ──

class TestSma:
    def test_basic(self, prices):
        result = sma(prices, 5)
        assert len(result) == len(prices)
        assert result.iloc[:4].isna().all()
        assert not result.iloc[4:].isna().any()

    def test_window_equals_length(self, prices):
        result = sma(prices, len(prices))
        assert not pd.isna(result.iloc[-1])

    def test_empty_input(self):
        result = sma(pd.Series([], dtype=float), 5)
        assert len(result) == 0

    def test_single_value(self):
        result = sma(pd.Series([42.0]), 1)
        assert result.iloc[0] == 42.0


# ── EMA ──

class TestEma:
    def test_basic(self, prices):
        result = ema(prices, 12)
        assert len(result) == len(prices)
        # EMA 从第一个值开始有输出
        assert not result.isna().any()

    def test_empty_input(self):
        result = ema(pd.Series([], dtype=float), 5)
        assert len(result) == 0


# ── MACD ──

class TestMacd:
    def test_basic(self, prices):
        dif, dea, hist = macd(prices)
        assert len(dif) == len(prices)
        assert len(dea) == len(prices)
        assert len(hist) == len(prices)
        # hist = dif - dea
        valid = ~(dif.isna() | dea.isna())
        pd.testing.assert_series_equal(
            hist[valid], (dif - dea)[valid], check_names=False,
        )

    def test_custom_params(self, prices):
        dif, dea, hist = macd(prices, fast=5, slow=10, signal=3)
        assert not hist.iloc[-1:].isna().any()

    def test_empty_input(self):
        dif, dea, hist = macd(pd.Series([], dtype=float))
        assert len(dif) == 0


# ── RSI ──

class TestRsi:
    def test_range(self, prices):
        result = rsi(prices, 14)
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_window_nan(self, prices):
        result = rsi(prices, 14)
        # 前 period 个值中有 NaN（diff 消耗1个 + min_periods）
        assert result.iloc[:14].isna().any()

    def test_constant_price(self):
        # 常数价格 → RSI 应为 NaN (0/0)
        result = rsi(pd.Series([50.0] * 30), 14)
        # 没有变动，gain=loss=0，RS=NaN
        assert result.dropna().empty or result.iloc[-1] != result.iloc[-1]

    def test_empty_input(self):
        result = rsi(pd.Series([], dtype=float), 14)
        assert len(result) == 0


# ── Bollinger ──

class TestBollinger:
    def test_basic(self, prices):
        upper, middle, lower = bollinger(prices, 20, 2.0)
        valid = ~middle.isna()
        assert (upper[valid] >= middle[valid]).all()
        assert (lower[valid] <= middle[valid]).all()

    def test_middle_equals_sma(self, prices):
        _, middle, _ = bollinger(prices, 20)
        expected = sma(prices, 20)
        pd.testing.assert_series_equal(middle, expected, check_names=False)

    def test_empty_input(self):
        upper, middle, lower = bollinger(pd.Series([], dtype=float), 20)
        assert len(upper) == 0


# ── ATR ──

class TestAtr:
    def test_basic(self, ohlcv):
        high, low, close, _ = ohlcv
        result = atr(high, low, close, 14)
        assert len(result) == len(close)
        valid = result.dropna()
        assert (valid > 0).all()

    def test_window_nan(self, ohlcv):
        high, low, close, _ = ohlcv
        result = atr(high, low, close, 14)
        assert result.iloc[:13].isna().any()

    def test_empty_input(self):
        empty = pd.Series([], dtype=float)
        result = atr(empty, empty, empty, 14)
        assert len(result) == 0


# ── KDJ ──

class TestKdj:
    def test_basic(self, ohlcv):
        high, low, close, _ = ohlcv
        k, d, j = kdj(high, low, close)
        assert len(k) == len(close)
        valid_k = k.dropna()
        # K 值通常在 0-100 之间（J 可超出）
        assert (valid_k >= 0).all() and (valid_k <= 100).all()

    def test_j_formula(self, ohlcv):
        high, low, close, _ = ohlcv
        k, d, j = kdj(high, low, close)
        valid = ~(k.isna() | d.isna())
        expected_j = 3 * k - 2 * d
        pd.testing.assert_series_equal(
            j[valid], expected_j[valid], check_names=False,
        )

    def test_empty_input(self):
        empty = pd.Series([], dtype=float)
        k, d, j = kdj(empty, empty, empty)
        assert len(k) == 0


# ── Volume MA ──

class TestVolumeMa:
    def test_basic(self, ohlcv):
        _, _, _, volume = ohlcv
        result = volume_ma(volume, 20)
        assert len(result) == len(volume)
        assert result.iloc[:19].isna().all()
        assert not result.iloc[19:].isna().any()

    def test_equals_sma(self, ohlcv):
        _, _, _, volume = ohlcv
        result = volume_ma(volume, 10)
        expected = sma(volume, 10)
        pd.testing.assert_series_equal(result, expected, check_names=False)
