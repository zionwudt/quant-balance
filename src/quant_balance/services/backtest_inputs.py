"""回测输入定义与基础校验。"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_SHORT_WINDOW = 5
DEFAULT_LONG_WINDOW = 20
MAX_MA_WINDOW = 250

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class BacktestInputError(ValueError):
    """统一的输入校验异常。"""


@dataclass(slots=True)
class BacktestRequest:
    """一次回测请求的标准化输入。"""

    symbol: str
    start_date: str
    end_date: str
    initial_cash: float = 100_000.0
    short_window: int = DEFAULT_SHORT_WINDOW
    long_window: int = DEFAULT_LONG_WINDOW

    def validate(self) -> None:
        """在获取数据前先做字段级校验。"""

        if not self.symbol.strip():
            raise BacktestInputError("请填写股票代码，例如 600519.SH。")
        if not _DATE_PATTERN.match(self.start_date):
            raise BacktestInputError("start_date 格式不正确，请使用 YYYY-MM-DD。")
        if not _DATE_PATTERN.match(self.end_date):
            raise BacktestInputError("end_date 格式不正确，请使用 YYYY-MM-DD。")
        if self.start_date > self.end_date:
            raise BacktestInputError("start_date 不能晚于 end_date。")
        if self.initial_cash <= 0:
            raise BacktestInputError("初始资金必须大于 0。")
        if self.short_window < 2 or self.long_window < 3:
            raise BacktestInputError("均线参数过小，建议短均线 ≥ 2、长均线 ≥ 3。")
        if self.short_window >= self.long_window:
            raise BacktestInputError("均线参数不合理：短均线必须小于长均线。")
        if self.long_window > MAX_MA_WINDOW:
            raise BacktestInputError("均线窗口过大，当前演示建议不要超过 250。")
