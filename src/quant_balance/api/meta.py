"""API 元信息构建。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BacktestFieldGuide:
    """前端表单可直接展示的输入说明。"""

    supported_frequency: str
    recommended_ma_range: str
    notes: list[str]


@dataclass(slots=True)
class BacktestMeta:
    """初始化页面或前端表单所需的元信息。"""

    field_guide: BacktestFieldGuide
    server_mode: str


def get_backtest_field_guide() -> BacktestFieldGuide:
    """返回输入约束和结果解释提示。"""

    return BacktestFieldGuide(
        supported_frequency="通过 Tushare 获取 A 股日线数据。",
        recommended_ma_range="建议短均线 5-20，长均线 20-120，且短均线必须小于长均线。",
        notes=[
            "当前结果已包含 A 股手续费、过户费、卖出印花税。",
            "当前已支持最小公司行为处理：现金分红、送转/拆股，以及可选前复权视角。",
            "滑点、成交量约束与部分成交目前仍是简化模型。",
            "默认面向本地研究演示，不作为实盘建议。",
        ],
    )


def build_backtest_meta() -> BacktestMeta:
    """聚合 API 初始化阶段需要返回的说明信息。"""

    return BacktestMeta(
        field_guide=get_backtest_field_guide(),
        server_mode="api",
    )
