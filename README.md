# QuantBalance

**知衡（QuantBalance）**：面向量化交易的策略研究、风控与执行系统。

## Overview

QuantBalance is a project for building a disciplined quantitative trading workflow, covering:

- strategy research
- backtesting and evaluation
- risk control
- execution orchestration
- configuration and automation scripts

## Project Structure

```text
quant-balance/
├── backtest/     # Backtesting engines, adapters, reports
├── config/       # Environment and strategy configuration
├── docs/         # Project documentation
├── execution/    # Order execution and broker integrations
├── risk/         # Risk rules and position controls
├── scripts/      # Utility and automation scripts
├── src/          # Shared core code
├── strategies/   # Trading strategies
└── tests/        # Test cases
```

## Vision

QuantBalance focuses on three core capabilities:

1. **Research** — turn ideas into testable strategies
2. **Risk Control** — keep exposure, drawdown, and position sizing under control
3. **Execution** — connect validated strategies to reliable automated workflows

## Phase 1 Scope

Current first-phase assumptions:

- market: **A-share**
- initial capital: **100,000 CNY**
- frequency: **daily bar research/backtesting first**
- focus: **strategy research, risk control, and backtesting**
- excluded for now: **live broker integration and real-money trading**

## Status

Project initialized. The repository now includes a minimal Python scaffold, A-share account config, a basic strategy interface, a risk manager, and a simple backtest engine.
