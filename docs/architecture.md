# 架构

## 当前基线

截至 2026-03-24，QuantBalance 的主干架构已经切换到：

- `backtesting.py`：单股精细回测、交易明细、权益曲线、参数优化
- `vectorbt`：批量筛选、快速排名、信号级向量化扫描
- `FastAPI + Pydantic`：统一的 HTTP API
- `Tushare + SQLite`：行情、复权因子、股票池与财务缓存

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
  tushare_loader.py
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

`src/quant_balance/data/tushare_loader.py`

- 加载日线行情
- 维护 SQLite 缓存
- 返回 `backtesting.py` / `vectorbt` 可直接消费的 `DataFrame`
- 支持 `adjust="qfq"` 与 `adjust="none"`

`src/quant_balance/data/stock_pool.py`

- 提供 `get_pool_at_date(date)`
- 按历史上市状态构建股票池
- 用于规避幸存者偏差

`src/quant_balance/data/fundamental_loader.py`

- 提供 `load_financial_at(symbol, as_of_date)`
- 严格按 `ann_date` 对齐财务快照
- 用于规避未来函数

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

`src/quant_balance/services/screening_service.py`

- 编排 `get_pool_at_date() -> load_multi_dataframes() -> run_screening()`
- 负责信号校验、Top N 排名与返回结构

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

## 核心工作流

### 1. 批量筛选

```text
pool_date
  -> get_pool_at_date()
  -> load_multi_dataframes()
  -> run_screening()
  -> rankings
```

### 2. 单股精细回测

```text
symbol + date range
  -> load_dataframe()
  -> run_backtest()
  -> summary + trades + equity_curve
```

### 3. 参数优化

```text
symbol + param_ranges
  -> load_dataframe()
  -> optimize()
  -> best_params + best_stats
```

## 当前约束

- 只支持单股精细回测；组合级仓位撮合仍未实现
- 只支持日线数据
- 统一使用前复权价格作为研究视角
- A 股特有规则当前简化为标准佣金模型

## 已验证项

- `pytest` 全量通过
- `backtesting.py` 与 `vectorbt` 在“下一根成交”语义下收益对齐
- ASGI 集成冒烟覆盖核心 API

## 下一步重点

- Phase 5 自动化与信号体系
- Phase 6 结果持久化与对比
- Phase 7 模拟盘与执行适配
