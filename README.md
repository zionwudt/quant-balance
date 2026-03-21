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

## Backtest Report (MVP)

The current backtest result now includes a minimal `report` summary for research evaluation.

Example JSON shape:

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
  "max_drawdown_amount": 6200.0,
  "max_drawdown_start": "2026-01-15",
  "max_drawdown_end": "2026-02-03",
  "trades_count": 14,
  "fills_count": 28,
  "win_rate_pct": 57.14,
  "profit_loss_ratio": 1.46,
  "average_holding_days": 6.4,
  "turnover_ratio": 1.82,
  "benchmark_name": "CSI300",
  "benchmark_return_pct": 5.9,
  "excess_return_pct": 2.6
}
```

Notes:

- `max_drawdown_start/end` already expose the drawdown interval.
- benchmark is currently an extensibility slot: callers may pass a benchmark equity curve to compute relative return.
- factor attribution and richer tear sheets are intentionally deferred to later iterations.

## Status

Project initialized. The repository now includes a minimal Python scaffold, A-share account config, a basic strategy interface, a risk manager, and a simple backtest engine.

## Current A-share Backtest Assumptions

Implemented in the current MVP:

- buy/sell commissions and transfer fee
- sell-side stamp duty
- T+1 sell restriction
- no fill on suspended bars (`volume <= 0`)
- no buy fill at limit-up / no sell fill at limit-down

Planned next steps:

- configurable slippage model
- corporate actions and adjusted-price handling
- partial fills and volume constraints
