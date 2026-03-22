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
- configurable slippage model (`slippage_mode`, `slippage_rate`)
- minimal partial-fill support based on bar volume participation (`max_volume_participation`)
- buy-side partial fill fallback when requested quantity exceeds available cash or position-ratio cap
- simplified corporate actions support:
  - cash dividend (`cash_dividend_per_share`)
  - split / bonus-share style quantity adjustment (`share_ratio`)
  - optional forward-adjusted research view via `price_adjustment_mode="forward"`

### Corporate Actions / 复权口径（当前最小实现）

The current engine supports a deliberately minimal but practical A-share workflow:

1. **Raw bars + corporate actions**
   - pass `CorporateAction(...)` events into `BacktestEngine.run(..., corporate_actions=[...])`
   - on `ex_date`, the engine will:
     - add cash dividend to portfolio cash
     - adjust held quantity/average cost for split / bonus-share style actions

2. **Forward-adjusted research view**
   - set `AccountConfig(price_adjustment_mode="forward")`
   - the engine will transform pre-ex bars into a forward-adjusted series before strategy evaluation
   - this is meant for **daily-bar research/backtesting**, not a full institutional-grade adjustment pipeline

3. **Current boundaries**
   - supported: cash dividend + share-ratio adjustments
   - not yet supported: rights issue pricing, tax nuances, intraday ex-right handling, vendor-specific full adjustment chains

Planned next steps:

- richer microstructure assumptions (for example intraday matching, queue priority, more realistic volume curves)
- more complete corporate-action modeling only when a real research need appears

## Quickstart Demo CLI

After installation, you can run a minimal demo backtest directly from the terminal:

```bash
quant-balance demo
```

Or keep using the module entrypoint:

```bash
python -m quant_balance.main demo
```

Optional JSON output for scripting / regression checks:

```bash
quant-balance demo --json
```

The built-in demo uses `examples/demo_backtest.csv` and prints a compact summary including final equity, total return, max drawdown, and trades count.

## Local Testing

Install the package together with development/test dependencies:

```bash
python -m pip install -e .[dev]
```

Then run the test suite:

```bash
pytest -q
```

This keeps runtime dependencies minimal while giving contributors and CI a single, explicit way to prepare the local test environment.

## Local Demo Input Foundation

To make a future local Web demo more product-friendly, the repository now includes a demo input/validation foundation in `quant_balance.demo`:

- upload CSV / example data input modes by default
- local path mode only in developer mode
- CSV template generation and field guide helpers
- user-friendly validation messages for missing files, missing columns, invalid MA params, and empty data

This layer is framework-agnostic on purpose, so a later Flask/FastAPI/UI shell can reuse the same validation and copy rules.

## Browser Acceptance Baseline for Future Web Demo

To avoid shipping a future Web shell without product-level regression coverage, the repository now also defines a first browser acceptance baseline:

- stable `qb-*` / `data-testid` selector contract for the future page shell
- checklist covering home load, example flow, valid CSV upload, invalid CSV errors, invalid MA parameters, and result visibility
- documentation in `docs/web-demo-acceptance.md` for later browser automation implementation

This gives the upcoming Web MVP a concrete acceptance target before any Flask/FastAPI page is added.

## Local Web Demo Shell (MVP)

The repository now also ships a minimal browser-accessible local Web demo shell built on the Python standard library WSGI server.

Start it locally:

```bash
quant-balance web-demo --host 127.0.0.1 --port 8765
```

Or via module entrypoint:

```bash
python -m quant_balance.main web-demo --host 127.0.0.1 --port 8765
```

Then open <http://127.0.0.1:8765/demo> in your browser.

Current MVP capabilities:

- single-page form with stable `data-testid` anchors for future browser automation
- choose example data or paste uploaded CSV content into the page
- submit a backtest and view summary / closed trades / assumptions in one page
- surface the existing Chinese validation errors directly in the page

Current boundary:

- the "upload CSV" flow is temporarily implemented as textarea paste input, so the browser path is already testable before a real multipart upload widget is introduced
