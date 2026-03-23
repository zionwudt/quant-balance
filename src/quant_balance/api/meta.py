"""API 元信息构建。"""

from __future__ import annotations

from dataclasses import dataclass

from quant_balance.csv_loader import REQUIRED_CSV_COLUMNS, get_csv_template


@dataclass(slots=True)
class BacktestFieldGuide:
    """前端表单可直接展示的输入说明。"""

    supported_frequency: str
    csv_columns: tuple[str, ...]
    recommended_ma_range: str
    notes: list[str]


@dataclass(slots=True)
class BacktestMeta:
    """初始化页面或前端表单所需的元信息。"""

    input_options: list[dict[str, str | bool]]
    field_guide: BacktestFieldGuide
    csv_template: str
    example_csv: str
    server_mode: str
    developer_mode: bool


def get_backtest_field_guide() -> BacktestFieldGuide:
    """返回输入约束和结果解释提示。"""

    return BacktestFieldGuide(
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


def get_backtest_input_options(*, developer_mode: bool = False) -> list[dict[str, str | bool]]:
    """返回当前环境下允许的输入模式。"""

    options: list[dict[str, str | bool]] = [
        {"mode": "upload", "label": "上传 CSV", "default": True},
        {"mode": "example", "label": "示例数据", "default": False},
    ]
    if developer_mode:
        options.append({"mode": "path", "label": "本地路径（开发者模式）", "default": False})
    return options


def build_backtest_meta(*, developer_mode: bool = False, example_csv: str) -> BacktestMeta:
    """聚合 API 初始化阶段需要返回的说明信息。"""

    return BacktestMeta(
        input_options=get_backtest_input_options(developer_mode=developer_mode),
        field_guide=get_backtest_field_guide(),
        csv_template=get_csv_template(),
        example_csv=example_csv,
        server_mode="api",
        developer_mode=developer_mode,
    )
