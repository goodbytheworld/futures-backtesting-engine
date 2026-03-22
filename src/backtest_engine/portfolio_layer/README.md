# Portfolio Layer

This package implements the multi-strategy portfolio backtest engine.

It is responsible for:

- shared-capital accounting
- slot-level strategy execution
- rebalancing cadence
- target allocation
- portfolio artifact generation

## Subpackages

| Package | Purpose |
|---|---|
| `domain/` | portfolio config, signals, target contracts, policy enums |
| `adapters/` | legacy strategy compatibility for `BaseStrategy(engine)` |
| `scheduling/` | rebalance timing rules |
| `allocation/` | signal-to-target sizing |
| `execution/` | slot runners and portfolio ledger |
| `engine/` | `PortfolioBacktestEngine` event loop |
| `reporting/` | portfolio artifact serialization |

## Important Distinction

This package is not a thin wrapper around `src/backtest_engine/engine.py`.

- `src/backtest_engine/engine.py` runs one strategy against one primary symbol.
- `portfolio_layer/engine/engine.py` runs many strategy slots against a unified timeline with one shared equity pool.

Changes related to allocation, scheduler behavior, portfolio book accounting, slot orchestration, or cross-slot artifacts belong here.

## Output Contract

- baseline portfolio runs write to `results/portfolio/`
- scenario reruns write to `results/scenarios/<scenario_id>/portfolio/`
- bundles are consumed through `src/backtest_engine/services/artifact_service.py` and the terminal UI
