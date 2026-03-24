# 架构

## 当前基线

截至 2026-03-24，QuantBalance 的主干架构已经切换到：

- `backtesting.py`：单股精细回测、交易明细、权益曲线、参数优化
- `vectorbt`：批量筛选、快速排名、信号级向量化扫描
- `FastAPI + Pydantic`：统一的 HTTP API
- `AkShare / Baostock / Tushare + SQLite`：多源行情 + Tushare 股票池/财务缓存

旧的自研回测内核模块已经从主干移除：

- `core/market_rules.py`
- `core/risk.py`
- `core/corporate_actions.py`
- `core/strategy.py`
- `api/presenters.py`
- `services/backtest_inputs.py`

## 分层设计

```text
DATA LAYER
  market_loader.py
  tushare_loader.py
  akshare_loader.py
  baostock_loader.py
  market_cache.py
  common.py
  stock_pool.py
  fundamental_loader.py
        │
        ▼
ENGINE LAYER
  backtest.py     -> backtesting.py
  screening.py    -> vectorbt
  strategies.py   -> Strategy 类 + signal 函数
  report.py       -> 统计翻译器
        │
        ▼
SERVICE LAYER
  backtest_service.py
  screening_service.py
        │
        ▼
API LAYER
  app.py
  schemas.py
  meta.py
```

## 模块职责

### 数据层

`src/quant_balance/data/market_loader.py`

- 提供统一的 `load_dataframe()` 入口
- 负责按 provider 顺序回退：`akshare -> baostock -> tushare`
- 对非 Tushare provider 统一走本地 SQLite 缓存

`src/quant_balance/data/tushare_loader.py`

- 负责 Tushare 日线与复权因子处理
- 复用既有 SQLite 缓存表，保持兼容

`src/quant_balance/data/akshare_loader.py` / `src/quant_balance/data/baostock_loader.py`

- 提供 provider 级日线抓取实现
- 统一输出标准化 OHLCV 行格式

`src/quant_balance/data/stock_pool.py`

- 提供 `get_pool_at_date(date)`
- 按历史上市状态构建股票池
- 用于规避幸存者偏差
- 当前仍为 Tushare-first

`src/quant_balance/data/fundamental_loader.py`

- 提供 `load_financial_at(symbol, as_of_date)`
- 严格按 `ann_date` 对齐财务快照
- 用于规避未来函数
- 当前仍为 Tushare-first

### 引擎层

`src/quant_balance/core/strategies.py`

- `SmaCross`、`EmaCross`、`BuyAndHold`
- `sma_cross_signals()`、`ema_cross_signals()`
- 同时维护 `STRATEGY_REGISTRY` 和 `SIGNAL_REGISTRY`

`src/quant_balance/core/backtest.py`

- 薄包装 `backtesting.Backtest`
- 暴露 `run_backtest()` 和 `optimize()`
- 输出 `BacktestResult`

`src/quant_balance/core/screening.py`

- 延迟导入 `vectorbt`
- 对多只股票批量运行信号函数
- 输出排名表与明细结果

`src/quant_balance/core/report.py`

- 将 `backtesting.py` stats 标准化为稳定字典
- 将 `vectorbt` stats 标准化为稳定字典
- 将交易与权益曲线转换为 JSON 友好的结构

### 服务层

`src/quant_balance/services/backtest_service.py`

- 编排 `load_dataframe() -> run_backtest() / optimize()`
- 负责策略校验、参数透传与 API 返回结构
- 负责 JSON 序列化清洗
- 支持可选 `data_provider`

`src/quant_balance/services/screening_service.py`

- 编排 `get_pool_at_date() -> load_multi_dataframes() -> run_screening()`
- 负责信号校验、Top N 排名与返回结构
- 支持可选 `data_provider`

### API 层

`src/quant_balance/api/app.py`

当前公开端点：

- `GET /health`
- `GET /api/meta`
- `GET /api/strategies`
- `POST /api/backtest/run`
- `POST /api/backtest/optimize`
- `POST /api/screening/run`

`src/quant_balance/api/schemas.py`

- `BacktestRunRequest`
- `OptimizeRequest`
- `ScreeningRunRequest`

## 可观测性

当前主干统一使用 `logging` 标准库输出结构化日志，日志前缀为：

```text
[quant_balance][EVENT] {...JSON fields...}
```

核心事件：

- `CACHE_HIT` / `CACHE_MISS`：数据层缓存命中与未命中，字段使用 `symbol`、`start_date`、`end_date`、`adjust`、`data_provider`、`dataset`
- `BACKTEST_RUN`：单股精细回测，字段使用 `symbol`、`start_date`、`end_date`、`strategy`、`bars_count`、`data_provider`
- `BACKTEST_OPTIMIZE`：参数优化，字段使用 `symbol`、`start_date`、`end_date`、`strategy`、`maximize`、`param_ranges`、`best_params`
- `SCREENING_RUN`：批量筛选，字段使用 `pool_date`、`start_date`、`end_date`、`signal`、`top_n`、`total_screened`、`data_provider`
- `API_ERROR`：API 400/500 错误路径，字段使用 `endpoint`、`status_code`、`detail` 和请求上下文

事件会分别在数据层、引擎层、服务层与 API 层输出，但字段命名保持一致，避免跨层检索时术语漂移。

## 核心工作流

### 1. 批量筛选

```text
pool_date
  -> get_pool_at_date()
  -> load_multi_dataframes()
  -> load_dataframe(provider fallback)
  -> run_screening()
  -> rankings
```

### 2. 单股精细回测

```text
symbol + date range
  -> load_dataframe(provider fallback)
  -> run_backtest()
  -> summary + trades + equity_curve
```

### 3. 参数优化

```text
symbol + param_ranges
  -> load_dataframe(provider fallback)
  -> optimize()
  -> best_params + best_stats
```

## 当前约束

- 只支持单股精细回测；组合级仓位撮合仍未实现
- 只支持日线数据
- 统一使用前复权价格作为研究视角
- 股票池与财务数据仍主要依赖 Tushare，尚未做多 provider 统一抽象
- A 股特有规则当前简化为标准佣金模型

## 已验证项

- `pytest` 全量通过
- `backtesting.py` 与 `vectorbt` 在“下一根成交”语义下收益对齐
- ASGI 集成冒烟覆盖核心 API

## 下一步重点

- Phase 5 自动化与信号体系
- Phase 6 结果持久化与对比
- Phase 7 模拟盘与执行适配
