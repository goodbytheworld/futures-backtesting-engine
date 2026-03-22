# Module Map

Quick reference for the modules contributors are most likely to touch.

## Portfolio Layer

### `domain/`

Pure contracts and enums.

| Module | Main Types | Purpose |
|---|---|---|
| `contracts.py` | `PortfolioConfig`, `StrategySlot` | validated portfolio configuration |
| `signals.py` | `StrategySignal`, `TargetPosition` | strategy output and allocator target types |
| `policies.py` | `RebalancePolicy`, `ExecutionPolicy` | portfolio policy enums and execution settings |

### `adapters/`

| Module | Purpose |
|---|---|
| `legacy_strategy_adapter.py` | adapts `BaseStrategy(engine)` strategies into the portfolio engine |

### `scheduling/`

| Module | Purpose |
|---|---|
| `scheduler.py` | rebalance cadence decisions such as intrabar and daily scheduling |

### `allocation/`

| Module | Purpose |
|---|---|
| `allocator.py` | converts signals and equity into target contract sizes |

### `execution/`

| Module | Purpose |
|---|---|
| `portfolio_book.py` | shared ledger, cash, positions, equity history |
| `strategy_runner.py` | drives slot-local strategy instances and collects signals |

### `engine/`

| Module | Purpose |
|---|---|
| `engine.py` | `PortfolioBacktestEngine`, the portfolio event loop |

### `reporting/`

| Module | Purpose |
|---|---|
| `results.py` | persists portfolio artifacts and reports |

## Top-Level Backtest Engine

| Module | Purpose |
|---|---|
| `src/backtest_engine/engine.py` | single-asset event loop |
| `src/backtest_engine/execution.py` | order, fill, trade, and execution handling |
| `src/backtest_engine/portfolio.py` | single-engine portfolio/accounting object |
| `src/backtest_engine/settings.py` | runtime settings and instrument specs |

## Services Layer

These modules are the public orchestration boundary between adapters and engines.

| Module | Purpose |
|---|---|
| `services/single_run_service.py` | single-run workflow |
| `services/wfo_run_service.py` | walk-forward workflow |
| `services/portfolio_run_service.py` | portfolio workflow and scenario metadata assembly |
| `services/batch_run_service.py` | multi-scenario batch runs |
| `services/wfo_batch_run_service.py` | multi-scenario WFO batch runs |
| `services/artifact_service.py` | artifact discovery, bundle inspection, loading |
| `services/scenario_job_service.py` | dashboard scenario job preparation |
| `services/scenario_runner_service.py` | scenario rerun execution helpers |
| `services/paths.py` | results path resolution |

## CLI Adapters

These should stay thin.

| Module | Trigger | Delegates To |
|---|---|---|
| `cli/single.py` | `--backtest` | `services/single_run_service.py` |
| `cli/wfo.py` | `--wfo` | `services/wfo_run_service.py` |
| `cli/portfolio.py` | `--portfolio-backtest` | `services/portfolio_run_service.py` |
| `cli/batch.py` | `batch` | `services/batch_run_service.py` |
| `cli/wfo_batch.py` | `wfo-batch` | `services/wfo_batch_run_service.py` |

## Runtime UI

| Module | Purpose |
|---|---|
| `runtime/terminal_ui/README.md` | runtime overview, tabs, queue/stress-testing notes |
| `runtime/terminal_ui/app.py` | FastAPI app factory |
| `runtime/terminal_ui/composition.py` | dependency and lifecycle wiring |
| `runtime/terminal_ui/service.py` | artifact-loading and runtime query layer |
| `runtime/terminal_ui/routes_partials.py` | HTML partial endpoints |
| `runtime/terminal_ui/routes_charts.py` | chart JSON endpoints |
| `runtime/terminal_ui/routes_operations.py` | scenario and operational endpoints |

## Contributor Shortcut

If you are deciding where a change belongs:

- CLI flag parsing or dispatch -> `run.py` or `cli/`
- workflow orchestration -> `services/`
- bar-by-bar execution -> engine modules
- saved metrics or reports -> `analytics/`
- UI rendering or route handling -> `runtime/terminal_ui/`
