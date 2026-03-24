# 知衡（QuantBalance）

面向个人投资者的 A 股量化研究与回测系统。

当前主干已经完成一次回测内核重构：

- 单股精细回测基于 `backtesting.py`
- 批量筛选基于 `vectorbt`
- 行情支持 AkShare / Baostock / Tushare，多数据源自动回退并带本地缓存
- API 层基于 FastAPI + Pydantic

## 当前能力

- 单股精细回测：`sma_cross`、`ema_cross`、`buy_and_hold`、`macd`、`rsi`、`bollinger`、`grid`、`dca`、`ma_rsi_filter`
- 参数优化：基于 `backtesting.py Backtest.optimize()`
- 批量筛选：基于 `vectorbt` 的信号扫描与排名
- 多因子排名：公告日对齐基本面 + 权重打分的横截面排序
- 组合回测：基于 `vectorbt` 的等权 / 自定义权重再平衡研究
- 历史股票池：`get_pool_at_date()` + 行业 / 市值 / PE / ST / 次新过滤，避免幸存者偏差
- 财务快照：`load_financial_at()` 聚合 `daily_basic / income / balancesheet / cashflow / fina_indicator`，按公告日对齐，避免未来函数
- 数据缓存：SQLite 本地缓存日线、复权因子和多表基本面数据
- Web API：返回 JSON，便于前端或脚本消费

## 当前边界

- 市场：仅 A 股
- 频率：仅日线
- 用途：本地研究与原型验证，不作为实盘建议
- 交易规则：当前统一为 `backtesting.py` 标准佣金模型
- 暂不支持：组合级持仓撮合、分钟级数据、实盘下单

## 安装

```bash
pip install -e .
```

如果要启用 AkShare / Baostock 日线数据源：

```bash
pip install -e .[cn_data]
```

开发环境：

```bash
pip install -e .[dev]
```

## 配置

复制示例配置：

```bash
cp config/config.example.toml config/config.toml
```

编辑 `config/config.toml`：

```toml
[tushare]
token = "你的token"

[data]
daily_providers = ["akshare", "baostock", "tushare"]

[server]
host = "127.0.0.1"
port = 8765
```

Tushare token 获取地址：[tushare.pro/register](https://tushare.pro/register)

说明：

- `daily_providers` 决定日线行情优先级，默认顺序会优先走 `AkShare -> Baostock -> Tushare`
- 即使 `tushare` 放在兜底位，股票池和基本面快照当前仍然是 Tushare-first
- 如果请求体显式传入 `data_provider`，会覆盖默认回退链

首次使用时，如果 `config/config.toml` 不存在或 `[tushare].token` 为空，CLI 会打印引导信息并退出，不再等到请求行情时才抛出错误。

## 启动

```bash
quant-balance
```

默认地址：

- API 根地址：<http://127.0.0.1:8765>
- OpenAPI 文档：<http://127.0.0.1:8765/docs>

## API 概览

当前提供的核心端点：

- `GET /health`
- `GET /api/meta`
- `GET /api/config/status`
- `GET /api/strategies`
- `POST /api/factors/rank`
- `POST /api/stock-pool/filter`
- `POST /api/config/tushare-token`
- `POST /api/backtest/run`
- `POST /api/backtest/optimize`
- `POST /api/portfolio/run`
- `POST /api/screening/run`

四个行情研究类 `POST` 接口都支持可选字段 `data_provider`，可显式指定 `akshare`、`baostock` 或 `tushare`。

## 内置策略

`GET /api/strategies` 会返回当前可用策略与信号函数。当前内置策略如下：

- `sma_cross` / `ema_cross`：均线交叉，参数通过 `params` 传 `fast_period`、`slow_period`
- `macd`：MACD 金叉/死叉，参数使用 `fast_period`、`slow_period`、`signal_period`
- `rsi`：RSI 超卖反弹，参数使用 `period`、`oversold`、`overbought`
- `bollinger`：布林带上轨突破，参数使用 `period`、`num_std`
- `grid`：均线锚定网格，参数使用 `anchor_period`、`grid_pct`
- `dca`：定期定额买入，参数使用 `interval_days`、`trade_fraction`
- `ma_rsi_filter`：均线趋势 + RSI 过滤，参数使用 `fast_period`、`slow_period`、`rsi_period`、`rsi_threshold`、`exit_rsi`
- `buy_and_hold`：无额外参数

单股回测继续使用 `strategy + params`，批量筛选继续使用 `signal + signal_params`。
如需启用风险退出，可额外传入 `stop_loss_pct` / `take_profit_pct`，例如 `0.08` 表示 8%。

### `GET /api/config/status`

返回当前配置状态，包括：

- `config_exists`
- `token_configured`
- `connection_ok`
- `message`

适合前端首次使用引导页轮询或初始化时调用。

### `POST /api/config/tushare-token`

```json
{
  "token": "your-token",
  "validate_only": false
}
```

- `validate_only=true` 时只测试连接，不保存到磁盘
- `validate_only=false` 时验证成功后写入 `config/config.toml`

### `POST /api/backtest/run`

```json
{
  "symbol": "600519.SH",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "strategy": "sma_cross",
  "cash": 100000,
  "commission": 0.001,
  "params": {
    "fast_period": 5,
    "slow_period": 20,
    "stop_loss_pct": 0.08,
    "take_profit_pct": 0.2
  }
}
```

### `POST /api/backtest/optimize`

```json
{
  "symbol": "600519.SH",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "strategy": "sma_cross",
  "cash": 100000,
  "commission": 0.001,
  "maximize": "Sharpe Ratio",
  "param_ranges": {
    "fast_period": [4, 5, 6],
    "slow_period": [18, 20, 22]
  }
}
```

### `POST /api/stock-pool/filter`

```json
{
  "pool_date": "2024-01-01",
  "filters": {
    "industries": ["白酒"],
    "exclude_st": true,
    "min_listing_days": 180,
    "min_market_cap": 500000,
    "max_pe": 30
  }
}
```

### `POST /api/factors/rank`

```json
{
  "pool_date": "2024-01-01",
  "factors": [
    { "name": "roe", "weight": 0.4 },
    { "name": "pe", "weight": 0.25 },
    { "name": "pb", "weight": 0.2 },
    { "name": "dv_ratio", "weight": 0.15 }
  ],
  "pool_filters": {
    "industries": ["白酒"],
    "exclude_st": true
  },
  "top_n": 20
}
```

### `POST /api/screening/run`

```json
{
  "pool_date": "2024-01-01",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "signal": "sma_cross",
  "signal_params": {
    "fast": 5,
    "slow": 20,
    "stop_loss_pct": 0.08,
    "take_profit_pct": 0.2
  },
  "top_n": 20,
  "cash": 100000
}
```

### `POST /api/portfolio/run`

```json
{
  "symbols": ["600519.SH", "000858.SZ"],
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "allocation": "custom",
  "weights": {
    "600519.SH": 0.6,
    "000858.SZ": 0.4
  },
  "rebalance_frequency": "monthly",
  "cash": 100000,
  "commission": 0.001
}
```

## 架构概览

```text
src/quant_balance/
├── api/
│   ├── app.py              # FastAPI 路由
│   ├── meta.py             # API 元信息
│   └── schemas.py          # Pydantic 请求模型
├── core/
│   ├── backtest.py         # backtesting.py 封装
│   ├── factors.py          # 多因子标准化与加权排名
│   ├── portfolio.py        # vectorbt 组合回测
│   ├── screening.py        # vectorbt 批量筛选
│   ├── strategies.py       # 策略类 + 信号函数
│   ├── report.py           # 统计标准化与输出转换
│   └── data_adapter.py     # 多标的数据加载适配
├── data/
│   ├── market_loader.py    # 统一日线入口 + provider fallback
│   ├── tushare_loader.py   # Tushare 日线 / 复权
│   ├── akshare_loader.py   # AkShare 日线
│   ├── baostock_loader.py  # Baostock 日线
│   ├── market_cache.py     # 非 Tushare provider 行情缓存
│   ├── common.py           # data 层公共配置 / 错误 / provider 解析
│   ├── stock_pool.py       # 历史股票池 + 过滤器
│   └── fundamental_loader.py
├── services/
│   ├── backtest_service.py
│   ├── factor_service.py
│   ├── portfolio_service.py
│   ├── screening_service.py
│   └── stock_pool_service.py
└── main.py                 # CLI 入口
```

请求流：

```text
AkShare / Baostock / Tushare
            │
            ▼
   data/market_loader.py
            │
            ▼
data/*.py / services/*.py
      │
      ▼
core/backtest.py  -> backtesting.py
core/factors.py   -> factor ranking
core/portfolio.py -> vectorbt (portfolio)
core/screening.py -> vectorbt
            │
            ▼
        api/app.py
```

## 设计约束

- 回测与筛选统一使用前复权日线（`qfq`）
- `load_dataframe()` 支持 `provider=` 显式指定，或按 `[data].daily_providers` 自动回退
- 组合回测通过目标权重矩阵做再平衡，不重新引入旧的自研多标的撮合内核
- `load_financial_at()` 会把估值与财报字段聚合成稳定快照，其中财报类字段严格按 `ann_date` 过滤
- 股票池过滤始终建立在 `get_pool_at_date()` 的历史池之上，可叠加行业 / 市值 / PE / ST / 次新条件
- 多因子打分基于横截面标准化和加权总分，不再依赖旧的 `PortfolioStrategy` 设计
- `get_pool_at_date()` 基于历史上市状态构建股票池
- `backtesting.py` 负责单股精细回测
- `vectorbt` 负责批量扫描与组合研究，不承担单股交易明细输出

## 结构化日志

运行时会输出统一前缀的结构化日志：

```text
[quant_balance][EVENT] {...JSON fields...}
```

核心事件与字段约定：

- `CACHE_HIT` / `CACHE_MISS`：`symbol`、`start_date`、`end_date`、`adjust`、`data_provider`、`dataset`、`rows_count`
- `BACKTEST_RUN`：`symbol`、`start_date`、`end_date`、`strategy`、`cash`、`commission`、`bars_count`、`data_provider`
- `BACKTEST_OPTIMIZE`：`symbol`、`start_date`、`end_date`、`strategy`、`maximize`、`param_ranges`、`best_params`、`data_provider`
- `FACTORS_RANK`：`pool_date`、`factors`、`candidate_count`、`scored_count`、`top_n`
- `SCREENING_RUN`：`pool_date`、`start_date`、`end_date`、`signal`、`top_n`、`total_screened`、`data_provider`
- `API_ERROR`：`endpoint`、`status_code`、`detail`，以及对应请求的 `symbol` / `strategy` / `signal` / `pool_date`

默认日志级别为 `INFO`，可通过环境变量 `QUANT_BALANCE_LOG_LEVEL` 调整。

## 测试

运行测试：

```bash
.venv/bin/python -m pytest -q
```

当前基线已通过：

- 单元测试
- 服务层测试
- API 路由测试
- ASGI 集成冒烟测试
- `backtesting.py` / `vectorbt` 一致性测试

## 文档

- [架构说明](./docs/architecture.md)
- [演进路线图](./docs/roadmap.md)
- [Web 设计规范](./docs/web-design.md)
