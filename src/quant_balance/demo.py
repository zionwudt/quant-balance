from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import csv
import io

from quant_balance.models import MarketBar
from quant_balance.report import BacktestReport

REQUIRED_CSV_COLUMNS = ("date", "open", "high", "low", "close", "volume")
DEFAULT_SHORT_WINDOW = 5
DEFAULT_LONG_WINDOW = 20
MAX_MA_WINDOW = 250


class DemoValidationError(ValueError):
    """User-facing validation error for local demo input handling."""


@dataclass(slots=True)
class BacktestDemoRequest:
    input_mode: str
    symbol: str
    initial_cash: float = 100_000.0
    short_window: int = DEFAULT_SHORT_WINDOW
    long_window: int = DEFAULT_LONG_WINDOW
    csv_text: str | None = None
    csv_path: str | None = None
    developer_mode: bool = False

    def validate(self) -> None:
        if self.input_mode not in {"upload", "example", "path"}:
            raise DemoValidationError("请选择有效的数据来源：上传 CSV、示例数据，或在开发者模式下使用本地路径。")
        if self.input_mode == "path" and not self.developer_mode:
            raise DemoValidationError("本地路径模式仅在开发者模式下开放，默认请使用上传 CSV 或示例数据。")
        if not self.symbol.strip():
            raise DemoValidationError("请填写股票代码，例如 600519.SH。")
        if self.initial_cash <= 0:
            raise DemoValidationError("初始资金必须大于 0。")
        if self.short_window < 2 or self.long_window < 3:
            raise DemoValidationError("均线参数过小，建议短均线 ≥ 2、长均线 ≥ 3。")
        if self.short_window >= self.long_window:
            raise DemoValidationError("均线参数不合理：短均线必须小于长均线。")
        if self.long_window > MAX_MA_WINDOW:
            raise DemoValidationError("均线窗口过大，当前演示建议不要超过 250。")
        if self.input_mode == "upload" and not (self.csv_text or "").strip():
            raise DemoValidationError("请先上传 CSV 文件。")
        if self.input_mode == "path" and not (self.csv_path or "").strip():
            raise DemoValidationError("开发者路径模式下，请提供本地 CSV 路径。")


@dataclass(slots=True)
class DemoFieldGuide:
    supported_frequency: str
    csv_columns: tuple[str, ...]
    recommended_ma_range: str
    notes: list[str]


@dataclass(slots=True)
class DemoPageContext:
    input_options: list[dict[str, str | bool]]
    field_guide: DemoFieldGuide
    csv_template: str
    example_csv: str


@dataclass(slots=True)
class DemoResultContext:
    summary: dict[str, float | int | str | None]
    closed_trades: list[dict[str, object]]
    assumptions: list[str]
    chart_sections: list[str]


def get_demo_field_guide() -> DemoFieldGuide:
    return DemoFieldGuide(
        supported_frequency="当前仅支持日线 CSV（daily bar）。",
        csv_columns=REQUIRED_CSV_COLUMNS,
        recommended_ma_range="建议短均线 5-20，长均线 20-120，且短均线必须小于长均线。",
        notes=[
            "当前结果已包含 A 股手续费、过户费、卖出印花税。",
            "当前未包含滑点、复权处理、公司行为影响、成交量约束与部分成交。",
            "默认面向本地研究演示，不作为实盘建议。",
        ],
    )


def get_demo_input_options(*, developer_mode: bool = False) -> list[dict[str, str | bool]]:
    options: list[dict[str, str | bool]] = [
        {"mode": "upload", "label": "上传 CSV", "default": True},
        {"mode": "example", "label": "示例数据", "default": False},
    ]
    if developer_mode:
        options.append({"mode": "path", "label": "本地路径（开发者模式）", "default": False})
    return options


def get_csv_template() -> str:
    return "\n".join(
        [
            ",".join(REQUIRED_CSV_COLUMNS),
            "2026-01-05,10.00,10.30,9.90,10.20,1250000",
            "2026-01-06,10.25,10.50,10.10,10.45,1320000",
        ]
    )


def get_example_csv() -> str:
    return "\n".join(
        [
            ",".join(REQUIRED_CSV_COLUMNS),
            "2026-01-05,10.00,10.30,9.90,10.20,1250000",
            "2026-01-06,10.25,10.50,10.10,10.45,1320000",
            "2026-01-07,10.50,10.80,10.40,10.75,1180000",
            "2026-01-08,10.70,10.90,10.55,10.60,980000",
        ]
    )


def build_demo_page_context(*, developer_mode: bool = False) -> DemoPageContext:
    return DemoPageContext(
        input_options=get_demo_input_options(developer_mode=developer_mode),
        field_guide=get_demo_field_guide(),
        csv_template=get_csv_template(),
        example_csv=get_example_csv(),
    )



def build_demo_result_context(report: BacktestReport) -> DemoResultContext:
    guide = get_demo_field_guide()
    summary: dict[str, float | int | str | None] = {
        "initial_equity": report.initial_equity,
        "final_equity": report.final_equity,
        "total_return_pct": report.total_return_pct,
        "annualized_return_pct": report.annualized_return_pct,
        "annualized_volatility_pct": report.annualized_volatility_pct,
        "sharpe_ratio": report.sharpe_ratio,
        "sortino_ratio": report.sortino_ratio,
        "max_drawdown_pct": report.max_drawdown_pct,
        "max_drawdown_start": report.max_drawdown_start.isoformat() if report.max_drawdown_start else None,
        "max_drawdown_end": report.max_drawdown_end.isoformat() if report.max_drawdown_end else None,
        "trades_count": report.trades_count,
        "win_rate_pct": report.win_rate_pct,
        "turnover_ratio": report.turnover_ratio,
        "benchmark_name": report.benchmark_name,
        "benchmark_return_pct": report.benchmark_return_pct,
        "excess_return_pct": report.excess_return_pct,
    }
    return DemoResultContext(
        summary=summary,
        closed_trades=report.to_dict()["closed_trades"],
        assumptions=guide.notes,
        chart_sections=["summary", "trades", "equity_curve"],
    )



def load_demo_bars(request: BacktestDemoRequest) -> list[MarketBar]:
    request.validate()
    if request.input_mode == "example":
        csv_text = get_example_csv()
    elif request.input_mode == "upload":
        csv_text = request.csv_text or ""
    else:
        try:
            with open(request.csv_path or "", encoding="utf-8") as handle:
                csv_text = handle.read()
        except FileNotFoundError as exc:
            raise DemoValidationError("找不到你提供的 CSV 文件，请检查路径是否正确，或直接改用上传模式。") from exc

    bars = parse_csv_text_to_bars(csv_text=csv_text, symbol=request.symbol)
    if not bars:
        raise DemoValidationError("CSV 中没有可用数据，请确认文件不是空的，并且至少包含一行行情。")
    return bars


def parse_csv_text_to_bars(*, csv_text: str, symbol: str) -> list[MarketBar]:
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    if reader.fieldnames is None:
        raise DemoValidationError("CSV 为空，或缺少表头。")

    fieldnames = {name.strip() for name in reader.fieldnames}
    missing_columns = [column for column in REQUIRED_CSV_COLUMNS if column not in fieldnames]
    if missing_columns:
        raise DemoValidationError(
            "CSV 缺少必要字段：" + ", ".join(missing_columns) + "。请下载模板后按模板列名准备数据。"
        )

    bars: list[MarketBar] = []
    try:
        for row in reader:
            bars.append(
                MarketBar(
                    symbol=symbol,
                    date=date.fromisoformat((row["date"] or "").strip()),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
    except ValueError as exc:
        raise DemoValidationError(
            "CSV 中存在无法识别的数值或日期格式。请使用 YYYY-MM-DD 日期，并确保价格/成交量列都是数字。"
        ) from exc

    return bars
