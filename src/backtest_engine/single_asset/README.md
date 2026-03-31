# Single-Asset Package

Canonical single-engine code lives here.

## Modules

| Module | Purpose |
|---|---|
| `engine.py` | `BacktestEngine` event loop |
| `portfolio.py` | local portfolio/accounting model for the single engine |
| `fast_bar.py` | fast row adapter used by single-strategy execution paths |

## Notes

- Walk-forward optimization and standard single backtests should continue to flow through this package rather than through the portfolio layer.
