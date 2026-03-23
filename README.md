# 知衡（QuantBalance）— A股个人量化操作系统

面向个人投资者的 A 股量化策略研究、回测与风控系统。

## 快速开始

项目当前统一以 API 形式提供 Web 能力：

```bash
pip install -e .
quant-balance --open-browser
```

API 服务会启动在 <http://127.0.0.1:8765>，默认文档地址为 <http://127.0.0.1:8765/docs>。

可选参数：

```bash
quant-balance --host 0.0.0.0 --port 9000 --developer-mode
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--host` | 绑定地址 | `127.0.0.1` |
| `--port` | 绑定端口 | `8765` |
| `--open-browser` | 启动后自动打开接口文档页 | 关闭 |
| `--developer-mode` | 允许本地路径输入模式 | 关闭 |
| `--example-csv` | 示例 CSV 文件路径 | `examples/demo_backtest.csv` |

## 功能特性

- **日线回测引擎**：支持 A 股手续费、过户费、印花税、T+1 限制
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
├── src/quant_balance/
│   ├── backtest_inputs.py   # 回测输入定义与基础校验
│   ├── csv_loader.py        # CSV 解析与行情加载
│   ├── api/                 # FastAPI 接口层（HTTP、元信息、响应组装）
│   ├── core/                # 回测核心模块（模型、策略、引擎、报表、风控、市场规则）
│   ├── services/            # 共享业务编排层
│   └── main.py              # 统一入口（命令行解析 + 进程启动）
├── examples/                # 示例数据
├── tests/                   # 测试用例
└── docs/                    # 文档
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
