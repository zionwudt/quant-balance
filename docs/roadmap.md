# 知衡（QuantBalance）演进路线图

> 从单股研究工具，逐步演进为面向个人投资者的量化研究与执行系统。

## 当前状态

截至 2026-03-24，项目已经完成一次回测内核重构，当前主干基线如下：

- 单股精细回测：`backtesting.py`
- 批量筛选：`vectorbt`
- 数据层：Tushare + SQLite
- API：FastAPI + Pydantic

阶段进度：

| 阶段 | 状态 | 说明 |
| ------ | ------ | ------ |
| Phase 1：依赖 + 数据层适配 | 已完成 | 新增 `load_dataframe()` 与多标的数据适配 |
| Phase 2：引擎层替换 | 已完成 | 引入 `backtesting.py` / `vectorbt` / `strategies.py` |
| Phase 3：服务 + API 重构 | 已完成 | 新 API 与服务编排已落地 |
| Phase 4：清理与收尾 | 已完成 | 旧模块清理、测试重写、文档同步与 issue 同步已完成 |

## 当前能力盘点

| 维度 | 当前能力 | 当前空缺 |
| ------ | ------ | ------ |
| 回测 | 单股精细回测 + `vectorbt` 组合再平衡研究 | 组合级撮合与持仓管理 |
| 筛选 | 历史股票池 + 行业/市值/PE/ST/次新过滤 + 信号批量排名 | 多因子打分、条件筛选器 |
| 策略 | `sma_cross` / `ema_cross` / `buy_and_hold` / `macd` / `rsi` / `bollinger` / `grid` / `dca` / `ma_rsi_filter` | 组合级策略、更多因子过滤器 |
| 数据 | Tushare 日线、复权因子、多表基本面快照 | 分钟线、更丰富的另类数据 |
| 报告 | 收益、回撤、Sharpe、交易列表、权益曲线 | 基准对比、月度热力图、分年统计 |
| API | `/api/backtest/*`、`/api/portfolio/run`、`/api/screening/run` | 历史记录、信号中心、模拟盘相关 API |
| Web | 仅设计稿 | 尚未落地 Dashboard |

## 已完成的重构内容

### 数据层

- `tushare_loader.py` 支持 `load_dataframe()`
- `data_adapter.py` 支持批量加载 `dict[str, DataFrame]`
- `stock_pool.py` 提供历史时点股票池与可组合过滤器
- `fundamental_loader.py` 提供按公告日对齐的多表基本面快照与增量缓存

### 引擎层

- `core/strategies.py` 统一管理策略类与信号函数
- `core/backtest.py` 薄包装 `backtesting.py`
- `core/screening.py` 薄包装 `vectorbt`
- `core/report.py` 统一统计口径与 JSON 转换

### 服务 + API

- `backtest_service.py`
- `portfolio_service.py`
- `screening_service.py`
- `stock_pool_service.py`
- `api/schemas.py`
- `api/app.py`
- `api/meta.py`

### 已移除的旧实现

- `core/market_rules.py`
- `core/risk.py`
- `core/corporate_actions.py`
- `core/strategy.py`
- `api/presenters.py`
- `services/backtest_inputs.py`

## 当前 API 基线

### `GET /health`

健康检查。

### `GET /api/meta`

返回：

- 可用策略列表
- 可用信号列表
- 默认参数
- 前端初始化说明

### `GET /api/strategies`

返回：

- `strategies`
- `signals`

### `POST /api/backtest/run`

单股精细回测。

请求字段：

- `symbol`
- `start_date`
- `end_date`
- `strategy`
- `cash`
- `commission`
- `params`

### `POST /api/backtest/optimize`

参数优化。

请求字段：

- `symbol`
- `start_date`
- `end_date`
- `strategy`
- `cash`
- `commission`
- `maximize`
- `param_ranges`

### `POST /api/screening/run`

批量筛选。

请求字段：

- `pool_date`
- `start_date`
- `end_date`
- `signal`
- `signal_params`
- `pool_filters`
- `top_n`
- `cash`
- `symbols`（可选）

### `POST /api/stock-pool/filter`

历史股票池过滤。

请求字段：

- `pool_date`
- `filters`
- `symbols`（可选）

### `POST /api/portfolio/run`

组合回测。

请求字段：

- `symbols`
- `start_date`
- `end_date`
- `allocation`
- `weights`
- `rebalance_frequency`
- `cash`
- `commission`

## 核心约束

### 1. 幸存者偏差

股票池必须使用 `get_pool_at_date(date)` 构建，不能直接用当前上市列表。

过滤条件也必须建立在历史股票池之上，不能绕开该底座直接对当前全市场列表做筛选。

### 2. 未来函数

财务快照必须按 `ann_date <= as_of_date` 过滤。

### 3. 价格视角

当前研究默认使用前复权日线（`qfq`）。

如果未来要同时引入“研究价格”和“执行价格”的双轨机制，需要在现有第三方引擎封装之外新增一层价格视角协调逻辑，而不是恢复旧的自研撮合内核。

## 后续阶段

## Phase 5：自动化与信号体系

### 5.1 定时调度

目标：盘后自动跑筛选与信号生成。

建议实现：

- `scheduler.py`
- APScheduler
- 扫描流程复用 `screening_service.py`

### 5.2 信号管理

目标：把“筛选结果 / 策略触发结果”落成可追踪对象。

建议范围：

- `signals` SQLite 表
- 今日信号 / 历史信号查询 API
- 信号状态流转与跟踪

### 5.3 消息推送

目标：把信号结果推送到企业微信、钉钉、邮件等渠道。

## Phase 6：结果持久化与对比

目标：保存回测结果，支持历史检索与横向对比。

建议范围：

- `result_store.py`
- 历史回测列表 API
- 单次回测详情 API
- 多次回测对比 API

## Phase 7：模拟盘与执行适配

目标：在不直接接券商的前提下，把信号转成可跟踪的模拟执行。

建议范围：

- `paper_trading.py`
- 信号导出（CSV / JSON / 券商脚本）
- `BrokerAdapter` 抽象层

## Phase 8：进阶分析

目标：补齐更强的研究能力。

优先方向：

- 分钟级数据
- 市场状态识别
- 收益归因
- 更多因子与轮动策略

## 文档关系

- [README](../README.md)：项目入口与使用说明
- [architecture.md](./architecture.md)：当前主干架构
- [web-design.md](./web-design.md)：未来 Web 端设计规范
