from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import csv
import io
import json
from pathlib import Path

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
    sample_size_warning: str | None = None
    run_context: dict[str, object] | None = None
    export_json: str | None = None
    equity_curve_points: list[dict[str, object]] | None = None


@dataclass(slots=True)
class DemoStableSelector:
    key: str
    selector: str
    purpose: str


@dataclass(slots=True)
class DemoAcceptanceScenario:
    scenario_id: str
    title: str
    goal: str
    steps: list[str]
    expected_outcomes: list[str]
    selectors: list[str]


@dataclass(slots=True)
class DemoAcceptanceChecklist:
    page_contract: list[DemoStableSelector]
    scenarios: list[DemoAcceptanceScenario]
    notes: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "page_contract": [asdict(selector) for selector in self.page_contract],
            "scenarios": [asdict(scenario) for scenario in self.scenarios],
            "notes": self.notes,
        }


def get_demo_field_guide() -> DemoFieldGuide:
    return DemoFieldGuide(
        supported_frequency="当前仅支持日线 CSV（daily bar）。",
        csv_columns=REQUIRED_CSV_COLUMNS,
        recommended_ma_range="建议短均线 5-20，长均线 20-120，且短均线必须小于长均线。",
        notes=[
            "当前结果已包含 A 股手续费、过户费、卖出印花税。",
            "当前已支持最小公司行为处理：现金分红、送转/拆股，以及可选前复权视角。",
            "滑点、成交量约束与部分成交目前仍是简化模型；当前演示 CSV 仍默认按普通 OHLCV 输入。",
            "若需严格复权研究，请同时传入对应公司行为事件。",
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
    example_path = Path(__file__).resolve().parents[2] / "examples" / "demo_backtest.csv"
    return example_path.read_text(encoding="utf-8")


def build_demo_page_context(*, developer_mode: bool = False) -> DemoPageContext:
    return DemoPageContext(
        input_options=get_demo_input_options(developer_mode=developer_mode),
        field_guide=get_demo_field_guide(),
        csv_template=get_csv_template(),
        example_csv=get_example_csv(),
    )



def build_demo_result_context(
    report: BacktestReport,
    *,
    run_context: dict[str, object] | None = None,
    equity_curve_points: list[dict[str, object]] | None = None,
) -> DemoResultContext:
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
    export_payload = {
        "summary": summary,
        "closed_trades": report.to_dict()["closed_trades"],
        "run_context": run_context or {},
        "assumptions": guide.notes,
        "sample_size_warning": report.sample_size_warning,
    }
    return DemoResultContext(
        summary=summary,
        closed_trades=report.to_dict()["closed_trades"],
        assumptions=guide.notes,
        chart_sections=["summary", "trades", "equity_curve", "run_context", "export"],
        sample_size_warning=report.sample_size_warning,
        run_context=run_context or {},
        export_json=json.dumps(export_payload, ensure_ascii=False, indent=2),
        equity_curve_points=equity_curve_points or [],
    )


def get_demo_stable_selectors() -> list[DemoStableSelector]:
    return [
        DemoStableSelector("page-root", "[data-testid='qb-demo-page']", "页面根容器，确认 demo 已成功加载。"),
        DemoStableSelector("input-mode", "[data-testid='qb-input-mode']", "输入模式切换区（示例数据 / 上传 CSV）。"),
        DemoStableSelector("csv-upload", "[data-testid='qb-upload-input']", "CSV 上传控件。"),
        DemoStableSelector("example-trigger", "[data-testid='qb-use-example']", "一键填充示例数据并运行。"),
        DemoStableSelector("symbol-input", "[data-testid='qb-symbol-input']", "股票代码输入框。"),
        DemoStableSelector("initial-cash-input", "[data-testid='qb-initial-cash-input']", "初始资金输入框。"),
        DemoStableSelector("short-window-input", "[data-testid='qb-short-window-input']", "短均线输入框。"),
        DemoStableSelector("long-window-input", "[data-testid='qb-long-window-input']", "长均线输入框。"),
        DemoStableSelector("submit-button", "[data-testid='qb-submit-backtest']", "提交回测按钮。"),
        DemoStableSelector("error-banner", "[data-testid='qb-demo-error']", "页面级中文错误提示区域。"),
        DemoStableSelector("summary-panel", "[data-testid='qb-result-summary']", "结果 summary 指标区域。"),
        DemoStableSelector("trades-table", "[data-testid='qb-result-trades']", "成交/平仓明细区域。"),
        DemoStableSelector("assumptions-panel", "[data-testid='qb-result-assumptions']", "关键假设说明区域。"),
    ]


def build_demo_acceptance_checklist() -> DemoAcceptanceChecklist:
    return DemoAcceptanceChecklist(
        page_contract=get_demo_stable_selectors(),
        scenarios=[
            DemoAcceptanceScenario(
                scenario_id="home-loads",
                title="打开首页成功",
                goal="确认本地 Web demo 页面可访问，且核心表单区域已经渲染。",
                steps=[
                    "启动本地 Web demo 服务。",
                    "浏览器访问 demo 首页。",
                    "等待页面根容器和提交按钮出现。",
                ],
                expected_outcomes=[
                    "页面标题或主说明可见。",
                    "输入模式区、股票代码、均线参数与提交按钮均可见。",
                    "页面不出现崩溃栈或白屏。",
                ],
                selectors=["page-root", "input-mode", "symbol-input", "submit-button"],
            ),
            DemoAcceptanceScenario(
                scenario_id="example-backtest",
                title="使用示例数据完成一次回测",
                goal="验证不依赖外部 CSV 时，用户也能走通最小 happy path。",
                steps=[
                    "打开首页。",
                    "选择示例数据模式，保留默认参数。",
                    "点击提交回测。",
                ],
                expected_outcomes=[
                    "结果页或结果区域出现 summary 指标。",
                    "trades 区域与 assumptions 区域可见。",
                    "页面不出现错误提示。",
                ],
                selectors=["example-trigger", "submit-button", "summary-panel", "trades-table", "assumptions-panel"],
            ),
            DemoAcceptanceScenario(
                scenario_id="upload-valid-csv",
                title="上传合法 CSV 完成一次回测",
                goal="验证上传 CSV 路径可以跑通，并输出完整结果。",
                steps=[
                    "打开首页。",
                    "上传合法日线 CSV。",
                    "填写股票代码并提交回测。",
                ],
                expected_outcomes=[
                    "页面显示 summary 指标。",
                    "页面展示 trades 明细。",
                    "不出现中文校验错误。",
                ],
                selectors=["csv-upload", "symbol-input", "submit-button", "summary-panel", "trades-table"],
            ),
            DemoAcceptanceScenario(
                scenario_id="upload-invalid-csv",
                title="上传非法 CSV，看到明确中文错误提示",
                goal="验证现有 CSV 校验文案能直接映射到 Web 层。",
                steps=[
                    "打开首页。",
                    "上传缺列、日期乱序或价格区间非法的 CSV。",
                    "点击提交回测。",
                ],
                expected_outcomes=[
                    "页面出现中文错误提示。",
                    "错误提示文案能说明具体问题，例如缺列、日期顺序或价格区间。",
                    "结果区域不会显示伪造成功结果。",
                ],
                selectors=["csv-upload", "submit-button", "error-banner"],
            ),
            DemoAcceptanceScenario(
                scenario_id="invalid-ma-params",
                title="短均线大于等于长均线时，看到明确提示",
                goal="验证表单参数校验能阻止明显无效组合进入回测。",
                steps=[
                    "打开首页。",
                    "填写短均线 >= 长均线的参数组合。",
                    "点击提交回测。",
                ],
                expected_outcomes=[
                    "页面出现明确中文提示，说明短均线必须小于长均线。",
                    "不会进入成功结果页。",
                ],
                selectors=["short-window-input", "long-window-input", "submit-button", "error-banner"],
            ),
            DemoAcceptanceScenario(
                scenario_id="result-metrics-visible",
                title="结果页显示关键 summary 指标与 trades",
                goal="确保用户能看到最关键的回测产出，而不是只看到成功提示。",
                steps=[
                    "使用示例数据或合法 CSV 成功运行一次回测。",
                    "检查结果区域内容。",
                ],
                expected_outcomes=[
                    "summary 至少包含 final_equity、total_return_pct、max_drawdown_pct、trades_count。",
                    "trades 区域可见，即使为空也要有稳定容器。",
                    "assumptions 区域可见，说明当前模型边界。",
                ],
                selectors=["summary-panel", "trades-table", "assumptions-panel"],
            ),
        ],
        notes=[
            "页面 MVP 落地后，优先按这些稳定 data-testid 绑定自动化脚本，避免选择器依赖文案和视觉样式。",
            "自动化优先覆盖用户路径，不追求像素级 UI 校验。",
            "若后续新增结果图表或多页路由，应继续沿用 qb-* 前缀的稳定选择器。",
        ],
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
        raise DemoValidationError("CSV 缺少表头，请至少包含 date, open, high, low, close, volume。")

    normalized_fieldnames = [field.strip() for field in reader.fieldnames]
    missing_columns = [column for column in REQUIRED_CSV_COLUMNS if column not in normalized_fieldnames]
    if missing_columns:
        raise DemoValidationError(f"CSV 缺少必要字段：{', '.join(missing_columns)}。请下载模板后按模板列名准备数据。")

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
            raise DemoValidationError(f"第 {index} 行存在无法识别的数值或日期格式，请检查 date/open/high/low/close/volume。") from exc

        if previous_date and bar_date < previous_date:
            raise DemoValidationError(f"CSV 日期顺序不正确：第 {index} 行 {bar_date.isoformat()} 早于上一行 {previous_date.isoformat()}。")
        if bar_date in seen_dates:
            raise DemoValidationError(f"CSV 存在重复交易日：{bar_date.isoformat()}。")
        if min(open_price, high_price, low_price, close_price) <= 0:
            raise DemoValidationError(f"第 {index} 行价格必须全部大于 0。")
        if volume < 0:
            raise DemoValidationError(f"第 {index} 行成交量不能为负数。")
        if high_price < low_price:
            raise DemoValidationError(f"第 {index} 行价格区间不合法：high 不能小于 low。")
        if not (low_price <= open_price <= high_price):
            raise DemoValidationError(f"第 {index} 行 open 必须落在 low 和 high 之间。")
        if not (low_price <= close_price <= high_price):
            raise DemoValidationError(f"第 {index} 行 close 必须落在 low 和 high 之间。")

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


def _print_module_entry_hint() -> int:
    import sys

    print(
        "quant_balance.demo 不是独立 CLI 入口。\n"
        "请改用：python -m quant_balance demo --help\n"
        "或：quant-balance demo --help",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(_print_module_entry_hint())
