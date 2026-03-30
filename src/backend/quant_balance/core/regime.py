"""市场状态识别（市场环境过滤）。

功能：
基于均线趋势和动量指标判断当前市场环境
- BULL: 牛市（上升趋势）
- BEAR: 熊市（下降趋势）
- SIDEWAYS: 震荡市

判断依据：
1. 短期均线 > 长期均线（趋势判断）
2. 趋势强度 > 阈值（避免假突破）
3. 动量 > 阈值（确认趋势方向）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

RegimeState = Literal["BULL", "BEAR", "SIDEWAYS"]


@dataclass(slots=True)
class RegimeDetector:
    """基于均线趋势和动量的简化市场状态识别器。"""

    short_window: int = 20
    long_window: int = 60
    momentum_window: int = 20
    trend_threshold: float = 0.02
    momentum_threshold: float = 0.03

    def detect(self, index_df: pd.DataFrame) -> RegimeState:
        """返回最近一根 K 线对应的市场状态。"""

        analysis = self.analyze(index_df)
        if analysis.empty:
            raise ValueError("index_df 不能为空")
        return str(analysis["regime"].iloc[-1])  # type: ignore[return-value]

    def detect_series(self, index_df: pd.DataFrame) -> pd.Series:
        """返回整段时间上的市场状态序列。"""

        analysis = self.analyze(index_df)
        return analysis["regime"].copy()

    def analyze(self, index_df: pd.DataFrame) -> pd.DataFrame:
        """返回包含状态和关键判定指标的分析结果。"""

        if index_df is None or index_df.empty:
            raise ValueError("index_df 不能为空")
        if "Close" not in index_df.columns:
            raise ValueError("index_df 必须包含 Close 列")

        close = pd.Series(index_df["Close"], dtype=float).dropna()
        if close.empty:
            raise ValueError("index_df.Close 不能为空")

        short_ma = close.rolling(
            self.short_window,
            min_periods=min(self.short_window, max(5, self.short_window // 2)),
        ).mean()
        long_ma = close.rolling(
            self.long_window,
            min_periods=min(self.long_window, max(10, self.long_window // 2)),
        ).mean()
        momentum = close.pct_change(self.momentum_window).fillna(0.0)
        trend_strength = (short_ma / long_ma - 1.0).replace([pd.NA, pd.NaT], 0.0)
        trend_strength = trend_strength.fillna(0.0)

        bull_mask = (
            (close >= short_ma)
            & (short_ma >= long_ma)
            & (trend_strength >= self.trend_threshold)
            & (momentum >= self.momentum_threshold)
        )
        bear_mask = (
            (close <= short_ma)
            & (short_ma <= long_ma)
            & (trend_strength <= -self.trend_threshold)
            & (momentum <= -self.momentum_threshold)
        )

        regime = pd.Series("SIDEWAYS", index=close.index, dtype="object")
        regime.loc[bull_mask] = "BULL"
        regime.loc[bear_mask] = "BEAR"

        return pd.DataFrame(
            {
                "close": close,
                "short_ma": short_ma,
                "long_ma": long_ma,
                "trend_strength_pct": trend_strength * 100.0,
                "momentum_pct": momentum * 100.0,
                "regime": regime,
            },
            index=close.index,
        )
