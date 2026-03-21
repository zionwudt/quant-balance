# Architecture

## Initial Direction

QuantBalance starts with a modular design around four core domains:

1. **Data** — market data ingestion and normalization
2. **Strategy** — research, signals, and portfolio logic
3. **Risk** — exposure limits, sizing rules, and drawdown controls
4. **Execution** — order routing, adapters, and execution workflows

## Suggested Early Milestones

- Build a minimal market data model
- Define strategy interfaces
- Create a backtest loop
- Add basic risk checks before execution
- Integrate one broker or exchange adapter
