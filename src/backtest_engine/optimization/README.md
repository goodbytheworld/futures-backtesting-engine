# Optimization Layer

This package contains parameter search and walk-forward validation logic for single-strategy research.

## Main Modules


| Module              | Purpose                                                                      |
| ------------------- | ---------------------------------------------------------------------------- |
| `optimizer.py`      | Optuna-driven parameter optimization for a single strategy                   |
| `wfv_optimizer.py`  | walk-forward orchestration over repeated in-sample and out-of-sample windows |
| `fold_generator.py` | rolling/purged fold construction for time-series validation                  |
| `objective.py`      | composite optimization score and penalties                                   |
| `cost_model.py`     | execution-friction model used during optimization                            |
| `validation.py`     | guardrails for valid optimization inputs                                     |


## Scope

This layer is about selecting and validating strategy parameters. It is not the place for:

- CLI parsing
- artifact browsing
- dashboard route logic
- portfolio allocation logic

## Engine Relationship

- optimization runs ultimately evaluate strategies through `BacktestEngine`
- walk-forward orchestration is triggered from `services/wfo_run_service.py`
- cache validation and strategy loading happen before entering this package

