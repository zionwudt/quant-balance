# 知衡（QuantBalance）

面向个人投资者的 A 股量化研究与回测系统。

当前主干已经完成一次回测内核重构：

- 单股精细回测基于 `backtesting.py`
- 批量筛选基于 `vectorbt`
- 行情支持 AkShare / Baostock / Tushare，多数据源自动回退并带本地缓存
- API 层基于 FastAPI + Pydantic

## 当前能力

- 单股精细回测：`sma_cross`、`ema_cross`、`buy_and_hold`
- 参数优化：基于 `backtesting.py Backtest.optimize()`
- 批量筛选：基于 `vectorbt` 的信号扫描与排名
- 历史股票池：`get_pool_at_date()` 避免幸存者偏差
- 财务快照：`load_financial_at()` 按公告日对齐，避免未来函数
- 数据缓存：SQLite 本地缓存日线、复权因子和财务数据
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
- 即使 `tushare` 放在兜底位，股票池和财务快照当前仍然是 Tushare-first
- 如果请求体显式传入 `data_provider`，会覆盖默认回退链

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
- `GET /api/strategies`
- `POST /api/backtest/run`
- `POST /api/backtest/optimize`
- `POST /api/screening/run`

三个 `POST` 接口都支持可选字段 `data_provider`，可显式指定 `akshare`、`baostock` 或 `tushare`。

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
    "slow_period": 20
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

### `POST /api/screening/run`

```json
{
  "pool_date": "2024-01-01",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "signal": "sma_cross",
  "signal_params": {
    "fast": 5,
    "slow": 20
  },
  "top_n": 20,
  "cash": 100000
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
│   ├── stock_pool.py       # 历史股票池
│   └── fundamental_loader.py
├── services/
│   ├── backtest_service.py
│   └── screening_service.py
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
core/screening.py -> vectorbt
            │
            ▼
        api/app.py
```

## 设计约束

- 回测与筛选统一使用前复权日线（`qfq`）
- `load_dataframe()` 支持 `provider=` 显式指定，或按 `[data].daily_providers` 自动回退
- `load_financial_at()` 严格按 `ann_date` 过滤
- `get_pool_at_date()` 基于历史上市状态构建股票池
- `backtesting.py` 负责单股精细回测
- `vectorbt` 负责批量扫描，不承担单股交易明细输出

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
