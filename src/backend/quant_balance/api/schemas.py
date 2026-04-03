"""API 请求/响应 Pydantic 模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

AssetType = Literal["stock", "convertible_bond"]
NotifyChannel = Literal["wecom", "dingtalk", "serverchan", "email"]
Timeframe = Literal["1d", "1min", "5min", "15min", "30min", "60min"]
MarketRegime = Literal["BULL", "BEAR", "SIDEWAYS"]


class StockPoolFiltersRequest(BaseModel):
    """股票池过滤条件。"""

    industries: list[str] = Field(default_factory=list, description="行业白名单，如 ['银行', '白酒']")
    min_market_cap: float | None = Field(None, ge=0, description="最小总市值（沿用 Tushare daily_basic.total_mv 口径）")
    max_market_cap: float | None = Field(None, ge=0, description="最大总市值（沿用 Tushare daily_basic.total_mv 口径）")
    min_pe: float | None = Field(None, description="最小 PE")
    max_pe: float | None = Field(None, description="最大 PE")
    exclude_st: bool = Field(False, description="是否排除 ST / *ST")
    min_listing_days: int | None = Field(None, ge=0, description="最小上市天数；用于过滤次新股")


class StockPoolFilterRequest(BaseModel):
    """股票池过滤请求。"""

    pool_date: str = Field(..., description="股票池基准日期 YYYY-MM-DD")
    filters: StockPoolFiltersRequest = Field(default_factory=StockPoolFiltersRequest)
    symbols: list[str] | None = Field(None, description="可选候选股票列表；传入时会与历史股票池取交集")
    data_provider: str | None = Field(
        None,
        description="可选行情数据源：tushare / akshare / baostock；不传则按配置顺序回退",
    )


class FactorSpecRequest(BaseModel):
    """因子配置。"""

    name: str = Field(..., description="因子名称，如 roe / pe / pb / market_cap")
    weight: float = Field(1.0, gt=0, description="因子权重")
    direction: Literal["higher_better", "lower_better"] | None = Field(
        None,
        description="可选方向；不传则使用内置默认方向",
    )


class FactorsRankRequest(BaseModel):
    """多因子打分请求。"""

    pool_date: str = Field(..., description="股票池基准日期 YYYY-MM-DD")
    factors: list[FactorSpecRequest] = Field(
        default_factory=lambda: [
            FactorSpecRequest(name="roe", weight=0.4),
            FactorSpecRequest(name="pe", weight=0.25),
            FactorSpecRequest(name="pb", weight=0.2),
            FactorSpecRequest(name="dv_ratio", weight=0.15),
        ],
        description="因子配置列表",
    )
    pool_filters: StockPoolFiltersRequest = Field(default_factory=StockPoolFiltersRequest, description="股票池过滤条件")
    market_regime: MarketRegime | None = Field(None, description="可选市场状态过滤：BULL / BEAR / SIDEWAYS")
    market_regime_symbol: str = Field("000300.SH", description="市场状态识别基准指数，默认沪深300")
    top_n: int = Field(50, gt=0, description="返回前 N 名")
    symbols: list[str] | None = Field(None, description="可选候选股票列表；传入时会与历史股票池取交集")
    data_provider: str | None = Field(
        None,
        description="可选行情数据源：tushare / akshare / baostock；不传则按配置顺序回退",
    )


class BacktestRunRequest(BaseModel):
    """单股精细回测请求。"""

    symbol: str = Field(..., description="标的代码，如 600519.SH / 110043.SH")
    start_date: str = Field(..., description="起始时间；日线传 YYYY-MM-DD，分钟线可传 YYYY-MM-DD HH:MM:SS")
    end_date: str = Field(..., description="结束时间；日线传 YYYY-MM-DD，分钟线可传 YYYY-MM-DD HH:MM:SS")
    asset_type: AssetType = Field("stock", description="资产类型：stock / convertible_bond")
    timeframe: Timeframe = Field("1d", description="K 线周期：1d / 1min / 5min / 15min / 30min / 60min")
    strategy: str = Field("sma_cross", description="策略名称")
    cash: float = Field(100_000.0, gt=0, description="初始资金")
    commission: float = Field(0.001, ge=0, description="佣金比例")
    slippage_mode: Literal["off", "spread", "commission"] = Field(
        "off",
        description="滑点模式：off / spread / commission",
    )
    slippage_rate: float = Field(0.0, ge=0, description="滑点比例")
    params: dict = Field(default_factory=dict, description="策略参数")
    benchmark_symbol: str | None = Field(
        None,
        description="可选基准代码；传入后会返回基准对比字段",
    )
    benchmark_asset_type: AssetType | None = Field(
        None,
        description="可选基准资产类型；不传则沿用 asset_type",
    )
    benchmark_data_provider: str | None = Field(
        None,
        description="可选基准行情数据源；不传则沿用 data_provider",
    )
    data_provider: str | None = Field(
        None,
        description="可选行情数据源：tushare / akshare / baostock；不传则按配置顺序回退",
    )

    @model_validator(mode="after")
    def validate_benchmark_options(self) -> "BacktestRunRequest":
        if self.benchmark_symbol is None and (
            self.benchmark_asset_type is not None or self.benchmark_data_provider is not None
        ):
            raise ValueError("benchmark_asset_type / benchmark_data_provider 需要配合 benchmark_symbol 一起传入")
        return self


class OptimizeConstraintRequest(BaseModel):
    """优化约束。"""

    left: str = Field(..., description="左侧参数名")
    operator: Literal["<", "<=", ">", ">=", "==", "!="] = Field(..., description="约束操作符")
    right_param: str | None = Field(None, description="右侧参数名；与 right_value 二选一")
    right_value: int | float | bool | str | None = Field(None, description="右侧常量；与 right_param 二选一")

    @model_validator(mode="after")
    def validate_right_operand(self) -> "OptimizeConstraintRequest":
        has_right_param = self.right_param is not None
        has_right_value = self.right_value is not None
        if has_right_param == has_right_value:
            raise ValueError("right_param 与 right_value 必须且只能传一个")
        return self


class WalkForwardRequest(BaseModel):
    """Walk-Forward 验证配置。"""

    train_bars: int = Field(..., ge=20, description="训练窗口 K 线数量")
    test_bars: int = Field(..., ge=5, description="验证窗口 K 线数量")
    step_bars: int | None = Field(None, ge=1, description="窗口滑动步长；默认等于 test_bars")
    anchored: bool = Field(False, description="是否使用锚定训练窗口")


class OptimizeRequest(BaseModel):
    """参数优化请求。"""

    symbol: str = Field(..., description="标的代码")
    start_date: str = Field(..., description="起始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    asset_type: AssetType = Field("stock", description="资产类型：stock / convertible_bond")
    strategy: str = Field("sma_cross", description="策略名称")
    cash: float = Field(100_000.0, gt=0)
    commission: float = Field(0.001, ge=0)
    maximize: str = Field("Sharpe Ratio", description="优化目标")
    param_ranges: dict = Field(..., description="参数搜索范围，如 {fast_period: [5,10,15]}")
    top_n: int = Field(5, gt=0, le=20, description="返回前 N 个候选参数组合")
    constraints: list[OptimizeConstraintRequest] = Field(default_factory=list, description="可选参数约束")
    walk_forward: WalkForwardRequest | None = Field(None, description="可选 Walk-Forward 验证配置")
    data_provider: str | None = Field(
        None,
        description="可选行情数据源：tushare / akshare / baostock；不传则按配置顺序回退",
    )


class ScreeningRunRequest(BaseModel):
    """批量选股筛选请求。"""

    pool_date: str = Field(..., description="股票池基准日期 YYYY-MM-DD")
    start_date: str = Field(..., description="回测起始时间；日线传 YYYY-MM-DD，分钟线可传 YYYY-MM-DD HH:MM:SS")
    end_date: str = Field(..., description="回测结束时间；日线传 YYYY-MM-DD，分钟线可传 YYYY-MM-DD HH:MM:SS")
    asset_type: AssetType = Field("stock", description="资产类型：stock / convertible_bond")
    timeframe: Timeframe = Field("1d", description="K 线周期：1d / 1min / 5min / 15min / 30min / 60min")
    signal: str = Field("sma_cross", description="信号函数名称")
    signal_params: dict = Field(default_factory=dict, description="信号参数")
    pool_filters: StockPoolFiltersRequest = Field(default_factory=StockPoolFiltersRequest, description="股票池过滤条件")
    market_regime: MarketRegime | None = Field(None, description="可选市场状态过滤：BULL / BEAR / SIDEWAYS")
    market_regime_symbol: str = Field("000300.SH", description="市场状态识别基准指数，默认沪深300")
    top_n: int = Field(20, gt=0, description="返回前 N 名")
    cash: float = Field(100_000.0, gt=0, description="初始资金")
    symbols: list[str] | None = Field(None, description="自定义候选股票列表（传入时会与历史股票池取交集）")
    data_provider: str | None = Field(
        None,
        description="可选行情数据源：tushare / akshare / baostock；不传则按配置顺序回退",
    )


class PortfolioRunRequest(BaseModel):
    """组合回测请求。"""

    symbols: list[str] = Field(..., min_length=1, description="股票代码列表")
    start_date: str = Field(..., description="回测起始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="回测结束日期 YYYY-MM-DD")
    allocation: Literal["equal", "custom"] = Field("equal", description="权重模式")
    weights: dict[str, float] = Field(default_factory=dict, description="自定义权重，如 {AAA: 0.6, BBB: 0.4}")
    rebalance_frequency: Literal["daily", "weekly", "monthly", "quarterly"] = Field(
        "monthly",
        description="再平衡频率",
    )
    cash: float = Field(100_000.0, gt=0, description="初始资金")
    commission: float = Field(0.001, ge=0, description="佣金比例")
    data_provider: str | None = Field(
        None,
        description="可选行情数据源：tushare / akshare / baostock；不传则按配置顺序回退",
    )


class PaperStartRequest(BaseModel):
    """开始模拟盘请求。"""

    strategy: str = Field("macd", description="信号策略名称")
    strategy_params: dict = Field(default_factory=dict, description="策略参数")
    symbols: list[str] = Field(..., min_length=1, description="跟踪股票池")
    initial_cash: float = Field(100_000.0, gt=0, description="初始资金")
    asset_type: AssetType = Field("stock", description="资产类型：stock / convertible_bond")
    start_date: str | None = Field(None, description="可选起始日期 YYYY-MM-DD；不传默认今天")
    data_provider: str | None = Field(
        None,
        description="可选行情数据源：tushare / akshare / baostock；不传则按配置顺序回退",
    )


class PaperPauseRequest(BaseModel):
    """暂停模拟盘请求。"""

    session_id: str | None = Field(None, description="可选模拟盘会话 ID；不传默认当前活跃会话")


class PaperStopRequest(BaseModel):
    """停止模拟盘请求。"""

    session_id: str | None = Field(None, description="可选模拟盘会话 ID；不传默认当前活跃会话")
    date: str | None = Field(None, description="可选结算日期 YYYY-MM-DD；不传默认今天")


class TushareTokenRequest(BaseModel):
    """Tushare token 保存/验证请求。"""

    token: str = Field(..., min_length=1, description="待验证或保存的 Tushare token")
    validate_only: bool = Field(
        False,
        description="仅测试连接，不落盘保存",
    )


class SchedulerRunRequest(BaseModel):
    """手动触发一次盘后扫描。"""

    trade_date: str | None = Field(
        None,
        description="可选扫描日期 YYYY-MM-DD；不传默认取今天",
    )
    force: bool = Field(
        True,
        description="非交易日时是否回退到最近一个交易日继续执行",
    )


class SignalStatusUpdateRequest(BaseModel):
    """更新信号处理状态。"""

    status: Literal["pending", "executed", "ignored", "expired"] = Field(
        ...,
        description="信号状态：pending / executed / ignored / expired",
    )


class NotifyTestRequest(BaseModel):
    """测试通知渠道连通性。"""

    enabled: list[NotifyChannel] = Field(
        ...,
        min_length=1,
        description="要测试的通知渠道列表",
    )
    title: str = Field(
        "知衡通知测试",
        description="测试通知标题",
    )
    content: str = Field(
        "这是一条来自 QuantBalance 的测试通知，用于验证消息渠道连通性。",
        description="测试通知正文",
    )
    wecom_webhook: str | None = Field(None, description="企业微信 Webhook")
    dingtalk_webhook: str | None = Field(None, description="钉钉 Webhook")
    dingtalk_secret: str | None = Field(None, description="钉钉加签 Secret")
    serverchan_sendkey: str | None = Field(None, description="Server酱 SendKey")
    email_receiver: str | None = Field(None, description="邮件接收人")
    email_smtp_host: str | None = Field(None, description="SMTP Host")
    email_smtp_port: int = Field(465, ge=1, le=65535, description="SMTP Port")
    email_sender: str | None = Field(None, description="邮件发件人")
    email_password: str | None = Field(None, description="SMTP 密码或授权码")
    email_username: str | None = Field(None, description="SMTP 用户名；不传时默认使用 sender")
    email_use_ssl: bool = Field(True, description="是否使用 SSL")
    email_starttls: bool = Field(True, description="非 SSL 时是否启用 STARTTLS")

    def to_notify_config(self) -> dict[str, object]:
        return {
            "notify": {
                "enabled": list(self.enabled),
                "wecom": {
                    "webhook": self.wecom_webhook or "",
                },
                "dingtalk": {
                    "webhook": self.dingtalk_webhook or "",
                    "secret": self.dingtalk_secret or "",
                },
                "serverchan": {
                    "sendkey": self.serverchan_sendkey or "",
                },
                "email": {
                    "receiver": self.email_receiver or "",
                    "smtp_host": self.email_smtp_host or "",
                    "smtp_port": self.email_smtp_port,
                    "sender": self.email_sender or "",
                    "password": self.email_password or "",
                    "username": self.email_username or "",
                    "use_ssl": self.email_use_ssl,
                    "starttls": self.email_starttls,
                },
            },
        }
