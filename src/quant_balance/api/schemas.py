"""API 请求/响应 Pydantic 模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BacktestRunRequest(BaseModel):
    """单股精细回测请求。"""

    symbol: str = Field(..., description="股票代码，如 600519.SH")
    start_date: str = Field(..., description="起始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    strategy: str = Field("sma_cross", description="策略名称")
    cash: float = Field(100_000.0, gt=0, description="初始资金")
    commission: float = Field(0.001, ge=0, description="佣金比例")
    params: dict = Field(default_factory=dict, description="策略参数")


class OptimizeRequest(BaseModel):
    """参数优化请求。"""

    symbol: str = Field(..., description="股票代码")
    start_date: str = Field(..., description="起始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    strategy: str = Field("sma_cross", description="策略名称")
    cash: float = Field(100_000.0, gt=0)
    commission: float = Field(0.001, ge=0)
    maximize: str = Field("Sharpe Ratio", description="优化目标")
    param_ranges: dict = Field(..., description="参数搜索范围，如 {fast_period: [5,10,15]}")


class ScreeningRunRequest(BaseModel):
    """批量选股筛选请求。"""

    pool_date: str = Field(..., description="股票池基准日期 YYYY-MM-DD")
    start_date: str = Field(..., description="回测起始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="回测结束日期 YYYY-MM-DD")
    signal: str = Field("sma_cross", description="信号函数名称")
    signal_params: dict = Field(default_factory=dict, description="信号参数")
    top_n: int = Field(20, gt=0, description="返回前 N 名")
    cash: float = Field(100_000.0, gt=0, description="初始资金")
    symbols: list[str] | None = Field(None, description="自定义股票列表（传入则忽略 pool_date）")
