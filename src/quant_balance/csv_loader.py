"""CSV 输入加载与解析。"""

from __future__ import annotations

import csv
import io
from datetime import date

from quant_balance.backtest_inputs import BacktestInputError, BacktestRequest
from quant_balance.core.models import MarketBar

REQUIRED_CSV_COLUMNS = ("date", "open", "high", "low", "close", "volume")


def get_csv_template() -> str:
    """返回最小可用 CSV 模板。"""

    return "\n".join(
        [
            ",".join(REQUIRED_CSV_COLUMNS),
            "2026-01-05,10.00,10.30,9.90,10.20,1250000",
            "2026-01-06,10.25,10.50,10.10,10.45,1320000",
        ]
    )


def get_example_csv() -> str:
    """返回内置示例 CSV。"""

    return "\n".join(
        [
            ",".join(REQUIRED_CSV_COLUMNS),
            "2026-01-05,10.00,10.30,9.90,10.20,1250000",
            "2026-01-06,10.25,10.50,10.10,10.45,1320000",
            "2026-01-07,10.50,10.80,10.40,10.75,1180000",
            "2026-01-08,10.70,10.90,10.55,10.60,980000",
        ]
    )


def load_bars(request: BacktestRequest) -> list[MarketBar]:
    """从上传文本、示例数据或本地路径加载行情。"""

    request.validate()
    if request.input_mode == "example":
        csv_text = request.csv_text or get_example_csv()
    elif request.input_mode == "upload":
        csv_text = request.csv_text or ""
    else:
        try:
            with open(request.csv_path or "", encoding="utf-8") as handle:
                csv_text = handle.read()
        except FileNotFoundError as exc:
            raise BacktestInputError("找不到你提供的 CSV 文件，请检查路径是否正确，或直接改用上传模式。") from exc

    bars = parse_csv_text_to_bars(csv_text=csv_text, symbol=request.symbol)
    if not bars:
        raise BacktestInputError("CSV 中没有可用数据，请确认文件不是空的，并且至少包含一行行情。")
    return bars


def parse_csv_text_to_bars(*, csv_text: str, symbol: str) -> list[MarketBar]:
    """把 CSV 文本解析成回测可消费的行情序列。"""

    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    if reader.fieldnames is None:
        raise BacktestInputError("CSV 缺少表头，请至少包含 date, open, high, low, close, volume。")

    normalized_fieldnames = [field.strip() for field in reader.fieldnames]
    missing_columns = [column for column in REQUIRED_CSV_COLUMNS if column not in normalized_fieldnames]
    if missing_columns:
        raise BacktestInputError(f"CSV 缺少必要字段：{', '.join(missing_columns)}。请下载模板后按模板列名准备数据。")

    bars: list[MarketBar] = []
    seen_dates: set[date] = set()
    previous_date: date | None = None

    for index, raw_row in enumerate(reader, start=2):
        row = {(key.strip() if key else key): value for key, value in raw_row.items()}
        try:
            bar_date = date.fromisoformat((row["date"] or "").strip())
            open_price = float((row["open"] or "").strip())
            high_price = float((row["high"] or "").strip())
            low_price = float((row["low"] or "").strip())
            close_price = float((row["close"] or "").strip())
            volume = float((row["volume"] or "").strip())
        except (TypeError, ValueError) as exc:
            raise BacktestInputError(f"第 {index} 行存在无法识别的数值或日期格式，请检查 date/open/high/low/close/volume。") from exc

        if previous_date and bar_date < previous_date:
            raise BacktestInputError(f"CSV 日期顺序不正确：第 {index} 行 {bar_date.isoformat()} 早于上一行 {previous_date.isoformat()}。")
        if bar_date in seen_dates:
            raise BacktestInputError(f"CSV 存在重复交易日：{bar_date.isoformat()}。")
        if min(open_price, high_price, low_price, close_price) <= 0:
            raise BacktestInputError(f"第 {index} 行价格必须全部大于 0。")
        if volume < 0:
            raise BacktestInputError(f"第 {index} 行成交量不能为负数。")
        if high_price < low_price:
            raise BacktestInputError(f"第 {index} 行价格区间不合法：high 不能小于 low。")
        if not (low_price <= open_price <= high_price):
            raise BacktestInputError(f"第 {index} 行 open 必须落在 low 和 high 之间。")
        if not (low_price <= close_price <= high_price):
            raise BacktestInputError(f"第 {index} 行 close 必须落在 low 和 high 之间。")

        bars.append(
            MarketBar(
                symbol=symbol,
                date=bar_date,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            )
        )
        previous_date = bar_date
        seen_dates.add(bar_date)

    return bars
