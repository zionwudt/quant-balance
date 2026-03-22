# Web Demo Browser Acceptance Baseline

This document defines the first browser-level acceptance baseline for the future QuantBalance local Web demo.

Goal: once the Web shell lands, we can quickly verify that the real user path still works in a browser instead of relying only on CLI or lower-level tests.

## Stable Selector Contract

Use stable `data-testid` selectors with the `qb-` prefix so browser automation does not depend on visible copy or layout details.

| Key | Selector | Purpose |
| --- | --- | --- |
| `page-root` | `[data-testid='qb-demo-page']` | Demo page root container |
| `input-mode` | `[data-testid='qb-input-mode']` | Upload/example mode switch |
| `csv-upload` | `[data-testid='qb-upload-input']` | CSV upload control |
| `example-trigger` | `[data-testid='qb-use-example']` | Trigger example-data run |
| `symbol-input` | `[data-testid='qb-symbol-input']` | Symbol input |
| `initial-cash-input` | `[data-testid='qb-initial-cash-input']` | Initial cash input |
| `short-window-input` | `[data-testid='qb-short-window-input']` | Short MA input |
| `long-window-input` | `[data-testid='qb-long-window-input']` | Long MA input |
| `submit-button` | `[data-testid='qb-submit-backtest']` | Submit button |
| `error-banner` | `[data-testid='qb-demo-error']` | User-facing error message area |
| `summary-panel` | `[data-testid='qb-result-summary']` | Summary metrics area |
| `trades-table` | `[data-testid='qb-result-trades']` | Trades list/table area |
| `assumptions-panel` | `[data-testid='qb-result-assumptions']` | Model assumptions area |

## First Acceptance Scenarios

### 1. Home page loads
- Open the local demo page
- Wait for page root and submit button
- Expect the main form to render without crash/blank page

### 2. Example data happy path
- Choose example mode
- Submit with default parameters
- Expect summary, trades area, and assumptions area to appear

### 3. Valid CSV upload path
- Upload a valid daily-bar CSV
- Fill symbol and submit
- Expect summary and trades output without validation errors

### 4. Invalid CSV error path
- Upload malformed CSV (missing columns / unsorted dates / invalid price range)
- Submit
- Expect a clear Chinese validation message in the error banner

### 5. Invalid MA parameter path
- Set short MA >= long MA
- Submit
- Expect a clear Chinese validation message and no success result

### 6. Result visibility contract
- After a successful run, verify the result area includes:
  - `final_equity`
  - `total_return_pct`
  - `max_drawdown_pct`
  - `trades_count`
- `trades-table` must exist even when there are zero trades
- `assumptions-panel` must remain visible so users can see current model boundaries

## Automation Guidance

- Prefer user-path checks over pixel-perfect UI checks
- Reuse existing Chinese validation copy from `quant_balance.demo`
- Keep selectors stable across refactors; if UI changes, update implementation before changing this contract
- When the Web MVP appears, convert these scenarios into executable browser automation (for example via `agent-browser`)
