# Config Package

Canonical runtime settings live here.

## Modules

| Module | Purpose |
|---|---|
| `backtest.py` | core engine, data, execution, batch, and path settings |
| `terminal_ui.py` | terminal runtime and dashboard payload settings |
| `scenario.py` | scenario-engine and artifact-retention defaults |

## Import Guidance

- Import settings models from `src.backtest_engine.config`.

## Design Rule

Keep reusable settings close to the bounded context they configure. Do not add new UI- or scenario-specific fields back into `BacktestSettings` unless they truly belong to the shared runtime contract.
