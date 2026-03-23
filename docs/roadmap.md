# 知衡（QuantBalance）演进路线图

> 从单标的回测工具，到可实战的个人量化交易系统。

## 现状总结

| 维度 | 当前能力 | 主要局限 |
|------|---------|---------|
| 策略 | 均线交叉、买入持有 | 仅 2 个策略，无因子体系 |
| 标的 | 单标的回测 | 不支持组合、无选股能力 |
| 数据 | Tushare 日线 + SQLite 缓存 | 无基本面、无分钟线 |
| 风控 | 仓位/回撤/手数校验 | 止损止盈未生效 |
| 报告 | Sharpe/Sortino/最大回撤等 | 无基准对比曲线、无月度热力图 |
| 交互 | FastAPI JSON | 无可视化前端 |
| 运行 | 手动触发 | 无定时任务、无消息推送 |
| 实盘 | 无 | 纯回测，无券商对接 |

---

## Phase 0：底层约束（贯穿所有阶段）

> 以下不是独立的开发阶段，而是**从第一行代码就必须遵守的规则**。
> 不处理这些问题，后续所有策略研究的结论都不可信。

### 0.1 回测三大偏差防护

#### 幸存者偏差（Survivorship Bias）

**问题**：只回测当前上市的股票，退市的亏损股被自动排除，收益率被系统性高估。

**解决方案**：

```python
# data/stock_pool.py — 股票池必须基于"历史时点"而非"当前时点"
def get_pool_at_date(date: str) -> list[str]:
    """
    返回某一天实际处于上市状态的所有股票。
    数据来源: Tushare stock_basic(list_status='L') + 退市股 stock_basic(list_status='D')
    判断逻辑: list_date <= date AND (delist_date IS NULL OR delist_date > date)
    """
```

**缓存**：Tushare `stock_basic` 全量拉取一次，存入 SQLite `stock_list` 表，含 `list_date`、`delist_date` 字段。

**影响范围**：Phase 2 的选股模块必须调用此接口，而非直接取当前股票列表。

#### 未来函数（Look-Ahead Bias）

**问题**：在回测中使用了"当时还不可能知道"的数据。最典型的场景：
- 用报告期末（`end_date`）而非公告日（`ann_date`）来对齐财务数据
- 用当日收盘价做当日买入决策（实际上收盘价要收盘后才知道）

**解决方案**：

```python
# data/fundamental_loader.py — 强制用公告日对齐
def load_financial_at(symbol: str, as_of_date: str) -> FinancialSnapshot | None:
    """
    返回截至 as_of_date 已公告的最新财务数据。
    SQL: WHERE ts_code = ? AND ann_date <= ? ORDER BY ann_date DESC LIMIT 1
    绝不使用 end_date 做时间筛选。
    """
```

**引擎层约束**：策略的 `generate_orders()` 只能看到**截至昨日收盘**的数据，当日的 bar 仅用于成交撮合。

#### 复权偏差（Price Adjustment Bias）

**问题**：前复权价格会随最新价格倒推调整，每天的历史价格都不一样。如果用前复权做回测，不同日期跑出的结果会不同。

**推荐方案**：
- **交易用不复权价格**：订单撮合、盈亏计算均基于真实成交价
- **指标用前复权价格**：计算均线、MACD 等技术指标时使用前复权，避免除权跳空产生假信号
- **分红再投资**：现金分红自动记入账户现金（当前 `corporate_actions.py` 已支持）

**实现**：`BacktestEngine` 内部维护两套价格序列，策略看前复权，撮合用不复权。

---

### 0.2 结构化日志

**问题**：当前无日志系统，策略逻辑越复杂越难排查问题。

**新增文件**：`src/quant_balance/core/logging.py`

**方案**：基于 Python 标准库 `logging`，不引入额外依赖。

```python
import logging

def setup_logger(name: str = "quant_balance", level: str = "INFO") -> logging.Logger:
    """配置带结构化前缀的日志器。"""
    ...

# 使用示例（引擎内部）:
logger.info("ORDER_REJECT | %s | reason=%s | price=%.2f", symbol, reason, price)
logger.info("FILL         | %s | side=%s | qty=%d | price=%.2f", symbol, side, qty, price)
logger.info("RISK_TRIM    | %s | target_ratio=%.1f%% | limit=%.1f%%", symbol, target, limit)
logger.info("STOP_LOSS    | %s | pnl_ratio=%.2f%% | threshold=%.2f%%", symbol, pnl, threshold)
```

**日志级别约定**：

| 级别 | 使用场景 |
|------|---------|
| DEBUG | 每日循环细节、指标计算中间值 |
| INFO | 成交、订单拒绝、止损触发、策略切换 |
| WARNING | 数据缺失跳过、样本量不足、参数超范围被截断 |
| ERROR | 数据加载失败、API 异常 |

**配置**：`config/config.toml` 新增：

```toml
[logging]
level = "INFO"          # DEBUG / INFO / WARNING / ERROR
file = ""               # 留空则输出到 stderr，填路径则写文件
```

---

### 0.3 首次使用引导

**问题**：新用户第一次启动时不知道要配 Tushare token，报错体验差。

**Web 端方案**（在 Phase 3 Web Dashboard 中实现）：

```
启动 → 检测 config/config.toml 是否存在且 token 非空
     → 否 → 全屏引导对话框:

     ┌────────────────────────────────────────┐
     │  欢迎使用知衡 QuantBalance              │
     │                                        │
     │  开始前需要配置 Tushare 数据源。         │
     │                                        │
     │  1. 前往 tushare.pro 注册账号           │
     │  2. 在个人中心获取 API Token            │
     │  3. 粘贴到下方输入框                    │
     │                                        │
     │  Token: [________________________________]│
     │                                        │
     │  [测试连接]  → ● 连接成功 / ✗ Token 无效 │
     │                                        │
     │                          [保存并开始 →]  │
     └────────────────────────────────────────┘
```

**CLI 端方案**（当前即可实现）：

```python
# main.py — 启动时检测
def check_config_or_guide():
    """检测配置，缺失时打印引导信息而非报错堆栈。"""
    if not config_exists():
        print("首次使用？请先配置 Tushare Token：")
        print("  1. 复制 config/config.example.toml → config/config.toml")
        print("  2. 在 [tushare] 下填入你的 token")
        print("  3. Token 获取地址: https://tushare.pro/register")
        sys.exit(1)
```

---

## Phase 1：核心能力补全

> 目标：从"单股验证"升级为"多股组合回测系统"，具备基本实用价值。

### 1.1 技术指标库

**目标**：提供可复用的指标计算函数，供策略调用。

**新增文件**：`src/quant_balance/core/indicators.py`

**实现清单**：

| 指标 | 函数签名 | 说明 |
|------|---------|------|
| SMA | `sma(closes: list[float], period: int) -> list[float\|None]` | 简单移动平均 |
| EMA | `ema(closes: list[float], period: int) -> list[float\|None]` | 指数移动平均 |
| MACD | `macd(closes, fast, slow, signal) -> (dif, dea, hist)` | MACD 三线 |
| RSI | `rsi(closes: list[float], period: int) -> list[float\|None]` | 相对强弱 |
| 布林带 | `bollinger(closes, period, num_std) -> (upper, mid, lower)` | 布林通道 |
| ATR | `atr(highs, lows, closes, period) -> list[float\|None]` | 真实波幅 |
| KDJ | `kdj(highs, lows, closes, n, m1, m2) -> (k, d, j)` | 随机指标 |
| 成交量MA | `volume_ma(volumes, period) -> list[float\|None]` | 量能均线 |

**设计原则**：
- 纯函数，输入 `list[float]`，输出 `list[float|None]`（前 N-1 个为 None）
- 零外部依赖（不引入 pandas/numpy/ta-lib），保持项目轻量
- 每个指标配套单元测试，用手算值做断言

**测试文件**：`tests/test_indicators.py`

---

### 1.2 更多内置策略

**目标**：提供 5-6 个经典策略覆盖不同交易风格。

**修改文件**：`src/quant_balance/core/strategy.py`

| 策略 | 类名 | 核心逻辑 |
|------|------|---------|
| MACD 策略 | `MACDStrategy` | DIF 上穿 DEA 买入，下穿卖出 |
| RSI 策略 | `RSIStrategy` | RSI < 30 买入，> 70 卖出（参数可配） |
| 布林带策略 | `BollingerStrategy` | 触下轨买入，触上轨卖出 |
| 网格交易 | `GridStrategy` | 按固定/百分比网格自动挂单 |
| 定投策略 | `DCAStrategy` | 每 N 个交易日定额买入 |
| 双均线+RSI | `MAWithRSIFilter` | 均线金叉 + RSI 过滤假信号 |

**API 变更**：`POST /api/backtests/run` 的请求体新增 `strategy` 字段：

```json
{
  "symbol": "600519.SH",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "strategy": "macd",
  "strategy_params": {"fast": 12, "slow": 26, "signal": 9},
  "initial_cash": 100000
}
```

**向后兼容**：不传 `strategy` 时默认 `"moving_average"`，保持现有行为。

---

### 1.3 止损 / 止盈执行

**目标**：让 `AccountConfig` 中已有的 `stop_loss_ratio` 真正生效。

**修改文件**：`src/quant_balance/core/backtest.py`

**实现方案**：在每日循环中，策略生成订单**之前**，扫描持仓：

```python
# 伪代码 - backtest.py 日循环中新增
for symbol, position in portfolio.positions.items():
    current_price = today_bar[symbol].close
    pnl_ratio = (current_price - position.avg_price) / position.avg_price

    if pnl_ratio <= -config.stop_loss_ratio:   # 止损
        止损卖出订单
    elif config.take_profit_ratio and pnl_ratio >= config.take_profit_ratio:  # 止盈
        止盈卖出订单
```

**模型变更**：`AccountConfig` 新增字段：

```python
take_profit_ratio: float = 0.0  # 0 表示不启用
```

**测试要点**：
- 触发止损时生成卖出订单并正确成交
- 止损订单仍受 T+1 和涨跌停规则约束
- 止盈 ratio=0 时不触发
- 止损与策略信号同日冲突时，止损优先

---

### 1.4 多标的组合回测

**目标**：支持同时回测多只股票，策略层面做组合决策。

**这是本阶段最大的改动，涉及多个文件。**

#### 1.4.1 数据层

**修改文件**：`src/quant_balance/data/tushare_loader.py`

新增批量加载：

```python
def load_bars_multi(
    symbols: list[str],
    start_date: str,
    end_date: str,
) -> dict[str, list[MarketBar]]:
    """返回 {symbol: [bars]} 字典，复用现有缓存逻辑。"""
```

#### 1.4.2 策略接口扩展

**修改文件**：`src/quant_balance/core/strategy.py`

当前 `generate_orders(bars, portfolio)` 中 `bars` 是单标的的 `list[MarketBar]`。

**方案**：新增 `PortfolioStrategy` 基类，与现有 `Strategy` 共存：

```python
class PortfolioStrategy(ABC):
    """多标的组合策略基类。"""

    @abstractmethod
    def generate_orders(
        self,
        bars_map: dict[str, list[MarketBar]],  # {symbol: 截至当日的bars}
        portfolio: Portfolio,
        today: date,
    ) -> list[Order]:
        ...
```

现有 `Strategy` 基类保持不变，引擎内部做适配。

#### 1.4.3 回测引擎

**修改文件**：`src/quant_balance/core/backtest.py`

核心变更：
- 按交易日历逐日推进，每日给策略传入所有标的截至当日的行情
- 订单匹配时按标的查找当日 bar
- 权益计算改为 `cash + sum(各持仓市值)`

#### 1.4.4 服务层

**修改文件**：`src/quant_balance/services/backtest_service.py`

新增 `run_portfolio_backtest(request)` 方法。

**API 端点**：`POST /api/backtests/portfolio`

```json
{
  "symbols": ["600519.SH", "000858.SZ", "601318.SH"],
  "start_date": "2023-01-01",
  "end_date": "2024-12-31",
  "strategy": "equal_weight_ma",
  "strategy_params": {"short_window": 10, "long_window": 30},
  "initial_cash": 500000,
  "max_positions": 3,
  "max_position_ratio": 0.35
}
```

---

## Phase 2：数据与选股能力

> 目标：从"给定股票回测"升级为"自主选股 + 回测"。

### 2.1 基本面数据接入

**目标**：从 Tushare 拉取财务数据，支持基本面因子。

**新增文件**：`src/quant_balance/data/fundamental_loader.py`

**数据项**：

| 数据 | Tushare 接口 | 缓存表 |
|------|-------------|--------|
| 日线指标 | `daily_basic` | `daily_basic`（PE/PB/总市值/流通市值/换手率） |
| 利润表 | `income` | `income`（营收/净利润/ROE） |
| 资产负债表 | `balancesheet` | `balancesheet` |
| 现金流量表 | `cashflow` | `cashflow` |
| 财务指标 | `fina_indicator` | `fina_indicator`（ROE/ROA/毛利率） |

**缓存策略**：复用现有 SQLite 库 `~/.quant_balance/cache.db`，每张表按 `(ts_code, ann_date)` 做主键，增量更新。

**对外接口**：

```python
def load_daily_basic(symbol: str, start: str, end: str) -> list[DailyBasic]:
    """PE/PB/市值/换手率等日频指标。"""

def load_financial(symbol: str, period: str) -> FinancialSnapshot:
    """某一期的财务快照（利润表+资产负债表+现金流）。"""
```

---

### 2.2 股票池筛选器

**目标**：按条件从全 A 股中筛选出目标股票池。

**新增文件**：`src/quant_balance/data/stock_pool.py`

**功能**：

```python
class StockPoolFilter:
    """股票池筛选器。"""

    def __init__(self):
        self._filters: list[Callable] = []

    def exclude_st(self) -> Self:
        """排除 ST / *ST。"""

    def exclude_new(self, days: int = 60) -> Self:
        """排除上市不足 N 天的次新股。"""

    def market_cap_range(self, min_cap: float, max_cap: float) -> Self:
        """流通市值范围（亿元）。"""

    def pe_range(self, min_pe: float, max_pe: float) -> Self:
        """市盈率范围。"""

    def industry(self, industries: list[str]) -> Self:
        """限定行业（申万一级）。"""

    def apply(self, date: str) -> list[str]:
        """返回符合条件的股票代码列表。"""
```

**数据依赖**：Tushare `stock_basic`（股票列表）+ `daily_basic`（日指标）。

**API 端点**：`POST /api/stock-pool/filter`

```json
{
  "date": "2024-12-31",
  "exclude_st": true,
  "exclude_new_days": 60,
  "market_cap_min": 50,
  "market_cap_max": 5000,
  "pe_min": 5,
  "pe_max": 40,
  "industries": ["食品饮料", "医药生物"]
}
```

**响应**：返回符合条件的股票代码列表 + 基础信息。

---

### 2.3 多因子打分选股

**目标**：基于多因子模型对股票打分排序，选出 Top N。

**新增文件**：`src/quant_balance/core/factors.py`

**内置因子**：

| 因子 | 类别 | 计算方式 |
|------|------|---------|
| EP | 价值 | 1 / PE_TTM |
| BP | 价值 | 1 / PB |
| ROE | 质量 | 净利润 / 净资产 |
| 营收增速 | 成长 | 同比营收增长率 |
| 20日动量 | 动量 | close / close_20d_ago - 1 |
| 20日换手率均值 | 流动性 | 近 20 日换手率均值 |
| 20日波动率 | 风险 | 近 20 日收益率标准差 |

**打分流程**：

```python
class FactorScorer:
    """多因子打分器。"""

    def add_factor(self, name: str, weight: float, ascending: bool = True) -> Self:
        """添加因子及权重。ascending=True 表示值越小得分越高。"""

    def score(self, stocks: list[str], date: str) -> list[ScoredStock]:
        """
        1. 获取每只股票每个因子的原始值
        2. 行业内中性化（可选）
        3. 排名百分位打分 (0-100)
        4. 加权汇总
        5. 返回排序结果
        """
```

**与回测结合**：新增 `FactorRotationStrategy(PortfolioStrategy)`：
- 每 N 个交易日重新打分
- 卖出不在 Top K 的持仓
- 买入新进入 Top K 的股票
- 等权或按分数加权分配仓位

**API 端点**：`POST /api/factors/rank`

```json
{
  "pool": ["600519.SH", "000858.SZ", "..."],
  "date": "2024-12-31",
  "factors": [
    {"name": "ep", "weight": 0.3},
    {"name": "roe", "weight": 0.3},
    {"name": "momentum_20d", "weight": 0.2},
    {"name": "volatility_20d", "weight": -0.2}
  ],
  "top_n": 10
}
```

---

### 2.4 参数优化与回测验证

**目标**：避免过拟合，提升策略可信度。

**新增文件**：`src/quant_balance/core/optimizer.py`

**功能模块**：

#### 网格搜索

```python
class GridSearchOptimizer:
    def __init__(self, strategy_cls, param_grid: dict[str, list]):
        """
        param_grid 示例:
        {"short_window": [5, 10, 15], "long_window": [20, 30, 60]}
        """

    def run(self, bars, config) -> list[OptimizationResult]:
        """遍历所有参数组合，返回排序后的结果列表。"""
```

#### Walk-Forward 验证

```python
class WalkForwardValidator:
    def __init__(
        self,
        train_days: int = 252,    # 训练窗口（约1年）
        test_days: int = 63,      # 测试窗口（约1季度）
        step_days: int = 63,      # 滑动步长
    ):
        ...

    def validate(self, bars, strategy_cls, param_grid, config) -> WalkForwardReport:
        """
        1. 按窗口切分数据
        2. 在训练集上做参数优化
        3. 用最优参数在测试集上跑回测
        4. 汇总所有测试集的表现
        """
```

**输出指标**：
- 样本内/样本外 Sharpe 衰减比
- 各窗口最优参数的稳定性（参数漂移度）
- 测试集累计收益曲线

**API 端点**：`POST /api/backtests/optimize`（异步执行，返回 task_id）

---

### 2.5 品种扩展：可转债与 ETF

**目标**：A 股散户量化最活跃的品种不只是股票，可转债和 ETF 的策略空间往往更大。

#### 可转债

**价值**：T+0 交易、无涨跌停（有临停机制）、有独特因子（转股溢价率、到期收益率），策略空间远大于股票。

**数据来源**：Tushare `cb_daily`（日线）、`cb_basic`（基本信息）、`cb_call`（强赎信息）

**新增文件**：`src/quant_balance/data/cb_loader.py`

**新增数据模型**：

```python
@dataclass(slots=True)
class ConvertibleBondBar(MarketBar):
    """可转债行情，继承 MarketBar 并扩展。"""
    convert_price: float = 0.0       # 转股价
    convert_value: float = 0.0       # 转股价值
    premium_rate: float = 0.0        # 溢价率 (%)
    ytm: float = 0.0                 # 到期收益率 (%)
```

**市场规则差异**：

| 规则 | 股票 | 可转债 |
|------|------|--------|
| T+N | T+1 | T+0 |
| 涨跌停 | ±10% | 无（临停：涨跌 20% 停 30min，30% 停至 14:57） |
| 最小交易单位 | 100 股 | 10 张 |
| 印花税 | 卖出 0.1% | 无 |
| 佣金 | 约 0.03% | 约 0.01% |

需在 `market_rules.py` 中新增 `CBMarketRules` 类。

**典型策略**：
- 双低策略（价格 + 溢价率双低轮动）
- 低溢价转股策略
- 强赎博弈策略

#### ETF

**价值**：部分品种 T+0（跨境、商品、货币类）、费率低、适合网格和趋势策略。

**数据来源**：Tushare `fund_daily`（日线）、`fund_basic`（基本信息）

**市场规则差异**：
- 部分 ETF 支持 T+0（需按 `fund_basic` 中的 `type` 字段判断）
- 最小交易单位：100 份
- 无印花税

**实现优先级**：可转债 > ETF（可转债的策略独特性更强）。

---

## Phase 3：报告增强与可视化

> 目标：让回测结果更直观、更便于复盘。

### 3.1 报告指标增强

**修改文件**：`src/quant_balance/core/report.py`

**新增指标**：

| 指标 | 说明 |
|------|------|
| Calmar Ratio | 年化收益 / 最大回撤 |
| 月度收益表 | 12×N 矩阵，每月收益率 |
| 滚动 Sharpe | 252 日滚动 Sharpe 曲线 |
| 分年统计 | 每年的收益/回撤/Sharpe |
| 持仓集中度 | HHI 指数 |
| 连续亏损天数 | 最长连续亏损周期 |

### 3.2 基准对比

**修改文件**：`src/quant_balance/core/report.py`、`services/backtest_service.py`

**方案**：
- `BacktestRequest` 新增 `benchmark: str = "000300.SH"`（沪深300）
- 回测时同步拉取基准行情
- 报告中计算超额收益、信息比率、Beta、Alpha
- 返回基准权益曲线供前端叠加展示

### 3.3 Web Dashboard

**目标**：提供专业级可视化前端，替代纯 JSON 输出。

> **完整设计规范见 [web-design.md](./web-design.md)**，包含配色系统、字体体系、组件规范、
> 每个页面的详细线框图、交互状态机、图表配色方案、键盘快捷键等。

**新增目录**：`src/quant_balance/web/`

**技术选型**：原生 ES Modules + CSS 变量，无 Node 构建链，FastAPI 直接 serve 静态文件。

**核心页面**（共 5 个，详见 web-design.md）：

| 页面 | 路由 | 交付阶段 |
|------|------|---------|
| 回测中心 | `/` | Web v0.1 |
| 选股研究 | `/#/stock-pool` | Web v0.3 |
| 模拟盘 | `/#/paper-trading` | Web v0.4 |
| 信号中心 | `/#/signals` | Web v0.4 |
| 设置 | `/#/settings` | Web v0.4 |

**设计关键词**：深色主题为主、数据密度优先、等宽数字字体、A 股/国际涨跌色可切换。

**Web 端独立交付节奏**（不阻塞后端 Phase 推进）：
- **Web v0.1**：单标的回测可视化（权益曲线 + 指标卡片 + 成交明细表）
- **Web v0.2**：多策略切换 + K 线图 + 买卖标记
- **Web v0.3**：组合回测 + 选股页面 + 月度热力图
- **Web v0.4**：模拟盘 + 信号中心 + 设置 + 浅色主题

---

## Phase 4：自动化与消息推送

> 目标：从"手动回测"到"每日自动运行 + 推送信号"。

### 4.1 定时调度

**新增文件**：`src/quant_balance/scheduler.py`

**方案**：使用 APScheduler（新增依赖），每日盘后定时触发。

```python
# 每个交易日 16:00 执行
scheduler.add_job(
    daily_scan,
    CronTrigger(hour=16, minute=0),
    misfire_grace_time=3600,
)
```

**`daily_scan` 流程**：
1. 判断今天是否为交易日（Tushare `trade_cal`）
2. 更新数据缓存
3. 运行配置的策略组
4. 生成信号列表
5. 推送通知

**依赖新增**：`pyproject.toml` 添加 `apscheduler>=3.10`

### 4.2 信号管理

**新增文件**：`src/quant_balance/core/signals.py`

```python
@dataclass
class Signal:
    symbol: str
    name: str           # 股票名称
    side: str           # BUY / SELL
    strategy: str       # 产生信号的策略名
    reason: str         # "MACD金叉" / "RSI超卖" 等
    price: float        # 当前价
    suggested_qty: int  # 建议数量（基于仓位管理）
    timestamp: datetime
```

**持久化**：SQLite 新表 `signals`，记录历史信号供复盘。

### 4.3 消息推送

**新增文件**：`src/quant_balance/notify/`

```
notify/
├── __init__.py
├── base.py          # Notifier 基类
├── wecom.py         # 企业微信机器人
├── dingtalk.py      # 钉钉机器人
├── serverchan.py    # Server酱 (微信推送)
└── email_notify.py  # SMTP 邮件
```

**基类接口**：

```python
class Notifier(ABC):
    @abstractmethod
    def send(self, title: str, content: str) -> bool:
        ...
```

**配置**：`config/config.toml` 新增：

```toml
[notify]
enabled = ["wecom"]

[notify.wecom]
webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"

[notify.dingtalk]
webhook = "https://oapi.dingtalk.com/robot/send?access_token=xxx"
secret = "SECxxx"
```

**推送内容示例**：

```
【知衡信号】2024-12-23

买入信号：
  600519.SH 贵州茅台 | MACD金叉 | 现价 1680.00 | 建议 1手

卖出信号：
  000858.SZ 五粮液 | RSI超买(78.5) | 现价 152.30

当前持仓：3 只 | 总市值：¥486,200 | 今日盈亏：+0.82%
```

---

## Phase 5：回测结果持久化与对比

> 目标：保存历史回测记录，支持策略迭代对比。

### 5.1 回测记录存储

**新增文件**：`src/quant_balance/data/result_store.py`

**SQLite 表结构**：

```sql
CREATE TABLE backtest_runs (
    run_id        TEXT PRIMARY KEY,   -- UUID
    created_at    TEXT NOT NULL,
    symbol        TEXT,
    symbols       TEXT,               -- JSON array (组合模式)
    strategy      TEXT NOT NULL,
    strategy_params TEXT,             -- JSON
    start_date    TEXT,
    end_date      TEXT,
    initial_cash  REAL,
    -- 核心指标快照
    total_return   REAL,
    annualized_return REAL,
    sharpe_ratio   REAL,
    sortino_ratio  REAL,
    max_drawdown   REAL,
    win_rate       REAL,
    trades_count   INTEGER,
    -- 完整结果
    full_report    TEXT              -- 完整 JSON，含权益曲线和成交明细
);
```

**API 端点**：
- `GET /api/backtests/history` — 列表（分页、筛选）
- `GET /api/backtests/{run_id}` — 单条详情
- `GET /api/backtests/compare?ids=a,b,c` — 多次回测对比

### 5.2 策略版本对比

在 Dashboard 中支持：
- 选择 2-3 条历史回测
- 叠加权益曲线对比
- 指标并排表格对比
- 参数差异高亮

---

## Phase 6：实盘对接（半自动）

> 目标：将策略信号转化为可执行的交易指令，人工确认后下单。

### 6.1 信号导出

**新增文件**：`src/quant_balance/execution/signal_export.py`

**导出格式**：
- CSV 文件（可导入券商客户端）
- QMT 格式的 Python 脚本
- JSON（供自定义对接）

```python
def export_signals_csv(signals: list[Signal], path: str) -> None:
    """导出为 CSV：代码,方向,数量,价格,策略,原因"""

def export_signals_qmt(signals: list[Signal], path: str) -> None:
    """导出为 QMT miniQMT 可执行的 Python 脚本。"""
```

### 6.2 模拟盘

**新增文件**：`src/quant_balance/execution/paper_trading.py`

**功能**：
- 内存中维护一个虚拟账户
- 接收信号后以次日开盘价模拟成交
- 每日更新持仓市值
- 记录所有模拟交易到 SQLite
- 提供与真实回测一致的绩效指标

**API 端点**：
- `POST /api/paper/start` — 开始模拟盘（初始资金、策略）
- `GET /api/paper/status` — 当前持仓和净值
- `POST /api/paper/stop` — 停止并生成报告

### 6.3 券商对接预留

**新增目录**：`src/quant_balance/execution/adapters/`

```
adapters/
├── __init__.py
├── base.py         # BrokerAdapter 抽象基类
├── qmt.py          # QMT/miniQMT 对接（迅投）
└── manual.py       # 手动确认模式（仅推送信号）
```

**基类**：

```python
class BrokerAdapter(ABC):
    @abstractmethod
    def place_order(self, signal: Signal) -> OrderResult: ...

    @abstractmethod
    def query_positions(self) -> list[Position]: ...

    @abstractmethod
    def query_balance(self) -> float: ...
```

> 注意：实盘对接务必加入**人工确认环节**，避免程序自动下单带来不可控风险。

---

## Phase 7：进阶分析能力

> 目标：提升策略研发深度。

### 7.1 分钟级数据

**修改文件**：`src/quant_balance/data/tushare_loader.py`

- 接入 Tushare `stk_mins` 接口（需更高积分）
- 缓存表 `minute_bars`，主键 `(ts_code, trade_time)`
- `MarketBar` 模型的 `date` 字段改为 `datetime`（保持向后兼容，日线部分 time 为 00:00）

**适用场景**：可转债 T+0 策略、ETF 日内网格。

### 7.2 市场状态识别

**新增文件**：`src/quant_balance/core/regime.py`

```python
class MarketRegime(Enum):
    BULL = "bull"           # 牛市
    BEAR = "bear"           # 熊市
    SIDEWAYS = "sideways"   # 震荡

class RegimeDetector:
    """基于均线 + 波动率的市场状态判断。"""

    def detect(self, index_bars: list[MarketBar]) -> MarketRegime:
        """
        判断逻辑：
        - 指数 > MA120 且 MA20 > MA60 → BULL
        - 指数 < MA120 且 MA20 < MA60 → BEAR
        - 其余 → SIDEWAYS
        """
```

**与策略结合**：
- 牛市：高仓位、动量策略
- 熊市：低仓位、防御策略
- 震荡：网格策略

### 7.3 归因分析

**新增文件**：`src/quant_balance/core/attribution.py`

- 持仓收益分解（个股贡献度）
- 行业配置贡献 vs 个股选择贡献（Brinson 模型简化版）
- 交易成本归因（手续费占比分析）

---

## 依赖管理规划

各阶段新增的 Python 依赖：

| Phase | 新增依赖 | 用途 |
|-------|---------|------|
| 0 | 无 | 标准库 logging + 数据校验逻辑 |
| 1 | 无 | 纯 Python 实现指标库 |
| 2 | 无 | 复用 Tushare 接口 |
| 2.5 | 无 | 可转债/ETF 复用 Tushare 接口 |
| 3 | 无（前端用本地 vendor） | ECharts / Lightweight Charts |
| 4 | `apscheduler>=3.10` | 定时任务调度 |
| 5 | 无 | SQLite 存储 |
| 6 | 视券商 SDK | QMT 需要 `xtquant` |
| 7 | 无 | 纯 Python |

**原则**：尽量不引入重型依赖（pandas/numpy），保持安装和部署的轻量性。

---

## 目录结构演进

完成全部 Phase 后的目标结构：

```
src/quant_balance/
├── api/
│   ├── app.py               # FastAPI 路由
│   ├── meta.py               # API 元信息
│   └── presenters.py         # 响应格式化
├── core/
│   ├── models.py             # 数据结构
│   ├── indicators.py         # [Phase 1] 技术指标库
│   ├── strategy.py           # 策略基类 + 内置策略
│   ├── factors.py            # [Phase 2] 因子计算与打分
│   ├── backtest.py           # 回测引擎
│   ├── optimizer.py          # [Phase 2] 参数优化
│   ├── report.py             # 报告生成
│   ├── risk.py               # 风控
│   ├── market_rules.py       # A股规则 + 可转债规则
│   ├── corporate_actions.py  # 公司行为
│   ├── signals.py            # [Phase 4] 信号管理
│   ├── regime.py             # [Phase 7] 市场状态
│   ├── attribution.py        # [Phase 7] 归因分析
│   └── logging.py            # [Phase 0] 结构化日志
├── data/
│   ├── tushare_loader.py     # 行情数据
│   ├── cb_loader.py          # [Phase 2.5] 可转债数据
│   ├── fundamental_loader.py # [Phase 2] 基本面数据
│   ├── stock_pool.py         # [Phase 2] 股票池（含历史退市股）
│   └── result_store.py       # [Phase 5] 结果存储
├── execution/                # [Phase 6]
│   ├── signal_export.py      # 信号导出
│   ├── paper_trading.py      # 模拟盘
│   └── adapters/             # 券商适配器
├── notify/                   # [Phase 4]
│   ├── base.py
│   ├── wecom.py
│   ├── dingtalk.py
│   └── serverchan.py
├── web/                      # [Phase 3] 详见 web-design.md
│   ├── index.html
│   └── static/
│       ├── css/
│       ├── js/
│       └── vendor/
├── services/
│   ├── backtest_service.py
│   └── backtest_inputs.py
├── scheduler.py              # [Phase 4] 定时调度
└── main.py                   # CLI 入口
```

---

## 实施建议

1. **Phase 0 不是一个独立阶段**——偏差防护和日志应从 Phase 1 第一行代码就融入，不要"后面再补"
2. **按 Phase 顺序推进**，每个 Phase 内部可以并行开发不同模块
3. **每个模块先写测试**，再写实现——项目当前测试覆盖良好，应保持这个习惯
4. **Phase 1 是基础**，后续所有功能都依赖多标的和指标库
5. **Phase 3 (Dashboard) 可提前启动**，因为它只依赖现有 API，与其他 Phase 无耦合
6. **可转债建议在 Phase 2 完成后优先做**，它的策略空间比继续加股票策略更大
7. **Phase 6 (实盘) 要谨慎**，建议先跑 3 个月模拟盘验证策略稳定性

---

## 相关文档

- [architecture.md](./architecture.md) — 系统架构设计
- [web-design.md](./web-design.md) — Web 端设计规范（配色、组件、页面线框图、交互细节）

---

*文档版本：v1.1 | 更新日期：2026-03-23 | 基于 QuantBalance 当前代码分析*
