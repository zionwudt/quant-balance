# 知衡（QuantBalance）— A股个人量化操作系统

面向个人投资者的 A 股量化策略研究、回测与风控系统。

## 快速开始

安装后直接启动 Web 服务：

```bash
pip install -e .
quant-balance --open-browser
```

浏览器会自动打开回测演示页面。你也可以手动访问 <http://127.0.0.1:8765/demo>。

可选参数：

```bash
quant-balance --host 0.0.0.0 --port 9000 --developer-mode
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--host` | 绑定地址 | `127.0.0.1` |
| `--port` | 绑定端口 | `8765` |
| `--open-browser` | 启动后自动打开浏览器 | 关闭 |
| `--developer-mode` | 允许本地路径输入模式 | 关闭 |
| `--example-csv` | 示例 CSV 文件路径 | `examples/demo_backtest.csv` |

## 功能特性

- **日线回测引擎**：支持 A 股手续费、过户费、印花税、T+1 限制
- **涨跌停处理**：涨停不可买入、跌停不可卖出
- **滑点与部分成交**：可配置滑点模型和成交量参与比例
- **公司行为**：现金分红、送转/拆股、可选前复权视角
- **风控管理**：持仓比例、最大回撤、最大持仓数控制
- **策略接口**：均线交叉策略示例，可扩展自定义策略
- **Web 演示**：本地浏览器回测界面，支持 CSV 上传和示例数据

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
│   ├── models.py            # 数据模型（行情、订单、持仓、账户配置）
│   ├── strategy.py          # 策略接口与均线交叉策略
│   ├── backtest.py          # 回测引擎
│   ├── report.py            # 回测报告生成
│   ├── risk.py              # 风控管理
│   ├── market_rules.py      # A股市场规则（涨跌停、T+1）
│   ├── corporate_actions.py # 公司行为处理（分红、送转）
│   ├── demo.py              # 回测演示逻辑（CSV 解析、验证）
│   ├── web_demo.py          # Web 服务（WSGI）
│   └── cli.py               # 命令行入口
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
