# 知衡（QuantBalance）— A股个人量化操作系统

面向个人投资者的 A 股量化策略研究、回测与风控系统。

## 快速开始

```bash
pip install -e .
```

### 配置

复制示例配置并填入你的 Tushare token：

```bash
cp config/config.example.toml config/config.toml
```

编辑 `config/config.toml`：

```toml
[tushare]
token = "你的token"   # 获取方式：https://tushare.pro/register

[server]
host = "127.0.0.1"
port = 8765
```

### 启动

```bash
quant-balance
```

API 服务会按 `config.toml` 中的配置启动，默认地址 <http://127.0.0.1:8765>，接口文档 <http://127.0.0.1:8765/docs>。

## 功能特性

- **日线回测引擎**：支持 A 股手续费、过户费、印花税、T+1 限制
- **行情数据**：通过 Tushare Pro 获取日线数据，SQLite 本地缓存
- **涨跌停处理**：涨停不可买入、跌停不可卖出
- **滑点与部分成交**：可配置滑点模型和成交量参与比例
- **公司行为**：现金分红、送转/拆股、可选前复权视角
- **风控管理**：持仓比例、最大回撤、最大持仓数控制
- **策略接口**：均线交叉策略示例，可扩展自定义策略
- **Web API**：提供面向前端页面的 JSON 接口与接口文档入口

## 回测报告示例

```json
{
  "initial_equity": 100000.0,
  "final_equity": 108500.0,
  "total_return_pct": 8.5,
  "annualized_return_pct": 22.14,
  "annualized_volatility_pct": 18.73,
  "sharpe_ratio": 1.18,
  "sortino_ratio": 1.74,
  "max_drawdown_pct": 6.2,
  "trades_count": 14,
  "win_rate_pct": 57.14
}
```

## 架构概览

```text
quant-balance/
├── config/                     # 项目配置
│   ├── config.example.toml     # 配置示例（提交到仓库）
│   └── config.toml             # 实际配置（gitignore 忽略）
├── src/quant_balance/
│   ├── main.py                 # 统一入口
│   ├── api/                    # FastAPI 接口层（HTTP、元信息、响应组装）
│   ├── core/                   # 回测核心模块（模型、策略、引擎、报表、风控、市场规则）
│   ├── data/                   # 数据获取层（Tushare + SQLite 缓存）
│   └── services/               # 业务编排层（请求校验、回测服务）
├── tests/                      # 测试用例
└── docs/                       # 文档
```

## 开发指南

安装开发依赖：

```bash
pip install -e .[dev]
```

运行测试：

```bash
pytest -q
```

## 当前边界

- 市场：仅 A 股
- 频率：仅日线
- 用途：本地研究演示，不作为实盘建议
- 暂不支持：实盘对接、多品种组合、分钟级数据
