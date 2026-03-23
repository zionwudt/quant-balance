"""回测输入定义与基础校验。"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SHORT_WINDOW = 5
DEFAULT_LONG_WINDOW = 20
MAX_MA_WINDOW = 250


class BacktestInputError(ValueError):
    """统一的输入校验异常。"""


@dataclass(slots=True)
class BacktestRequest:
    """一次回测请求的标准化输入。"""

    input_mode: str
    symbol: str
    initial_cash: float = 100_000.0
    short_window: int = DEFAULT_SHORT_WINDOW
    long_window: int = DEFAULT_LONG_WINDOW
    csv_text: str | None = None
    csv_path: str | None = None
    developer_mode: bool = False

    def validate(self) -> None:
        """在读取文件或解析 CSV 前先做字段级校验。"""

        if self.input_mode not in {"upload", "example", "path"}:
            raise BacktestInputError("请选择有效的数据来源：上传 CSV、示例数据，或在开发者模式下使用本地路径。")
        if self.input_mode == "path" and not self.developer_mode:
            raise BacktestInputError("本地路径模式仅在开发者模式下开放，默认请使用上传 CSV 或示例数据。")
        if not self.symbol.strip():
            raise BacktestInputError("请填写股票代码，例如 600519.SH。")
        if self.initial_cash <= 0:
            raise BacktestInputError("初始资金必须大于 0。")
        if self.short_window < 2 or self.long_window < 3:
            raise BacktestInputError("均线参数过小，建议短均线 ≥ 2、长均线 ≥ 3。")
        if self.short_window >= self.long_window:
            raise BacktestInputError("均线参数不合理：短均线必须小于长均线。")
        if self.long_window > MAX_MA_WINDOW:
            raise BacktestInputError("均线窗口过大，当前演示建议不要超过 250。")
        if self.input_mode == "upload" and not (self.csv_text or "").strip():
            raise BacktestInputError("请先上传 CSV 文件。")
        if self.input_mode == "path" and not (self.csv_path or "").strip():
            raise BacktestInputError("开发者路径模式下，请提供本地 CSV 路径。")
