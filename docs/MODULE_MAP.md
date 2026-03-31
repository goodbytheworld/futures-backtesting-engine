# Module Map

Quick reference for contributors deciding where code belongs.

## Canonical Packages

### `src/backtest_engine/config/`

| Module | Purpose |
|---|---|
| `backtest.py` | shared runtime settings for data, execution, risk, batch, and paths |
| `terminal_ui.py` | terminal runtime and dashboard settings |
| `scenario.py` | scenario-engine defaults and retention settings |

### `src/backtest_engine/execution/`

| Module | Purpose |
|---|---|
| `__init__.py` | `Order`, `Fill`, `Trade`, `ExecutionHandler` |
| `order_book.py` | resting-order registry for single-asset execution |
| `spread_model.py` | deterministic spread tick model |
| `time_controls.py` | trading-session and EOD helpers |

### `src/backtest_engine/single_asset/`

| Module | Purpose |
|---|---|
| `engine.py` | `BacktestEngine`, the canonical single-asset event loop |
| `portfolio.py` | local portfolio/accounting model for the single engine |
| `fast_bar.py` | fast bar adapter used inside the single-engine path |

### `src/backtest_engine/portfolio_layer/`

| Area | Purpose |
|---|---|
| `domain/` | portfolio config, contracts, signals, policies |
| `adapters/` | legacy strategy compatibility |
| `allocation/` | signal-to-target sizing |
| `execution/` | strategy runner, book, and bridge execution helpers |
| `engine/` | `PortfolioBacktestEngine` event loop |
| `reporting/` | artifact serialization and portfolio reports |

### `src/backtest_engine/services/`

| Module | Purpose |
|---|---|
| `single_run_service.py` | single-run workflow |
| `wfo_run_service.py` | walk-forward workflow |
| `portfolio_run_service.py` | portfolio workflow and scenario metadata assembly |
| `batch_run_service.py` | multi-scenario batch runs |
| `wfo_batch_run_service.py` | multi-scenario WFO batch runs |
| `artifact_service.py` | artifact discovery, bundle inspection, loading |
| `scenario_job_service.py` | dashboard scenario job preparation |
| `scenario_runner_service.py` | scenario rerun execution helpers |
| `paths.py` | results path resolution |
| `worker_manager.py` | compatibility facade for managed worker/redis lifecycle |

### `src/backtest_engine/runtime/terminal_ui/`

| Module | Purpose |
|---|---|
| `app.py` | FastAPI app factory |
| `composition.py` | dependency and lifecycle wiring |
| `service.py` | artifact-loading and runtime query layer |
| `routes_partials.py` | HTML partial endpoints |
| `routes_charts.py` | chart JSON endpoints |
| `routes_operations.py` | scenario and operational endpoints |
| `exit_charts/` | topic-split exit-analysis chart builders |
| `static/charts_shared.js` | shared chart loading and resize utilities |

### `src/backtest_engine/optimization/`

| Module | Purpose |
|---|---|
| `optimizer.py` | Optuna search and slice evaluation |
| `wfv_optimizer.py` | fold orchestration |
| `wfv_report.py` | fold models and report formatting |
| `optuna_runtime.py` | optional Optuna runtime helpers |

## Strategy Filters

| Module | Purpose |
|---|---|
| `src/strategies/filters/core.py` | shared indicator/config helpers |
| `src/strategies/filters/volatility.py` | volatility, shock, and stretch filters |
| `src/strategies/filters/trend.py` | trend T-stat filter |
| `src/strategies/filters/stationarity.py` | ADF and half-life filters |
| `src/strategies/filters/kalman.py` | Kalman beta estimator |

## CLI Adapters

| Module | Trigger | Delegates To |
|---|---|---|
| `cli/main_parser.py` | `run.py` startup | argparse construction and single-run overrides |
| `cli/lightweight_batch.py` | `batch`, `wfo-batch` | lightweight positional batch parsing |
| `cli/runtime_dashboard.py` | `--dashboard` | terminal UI launch helpers |
| `cli/data_validation.py` | `--validate-data` | cache validation reporting |
| `cli/single.py` | `--backtest` | `services/single_run_service.py` |
| `cli/wfo.py` | `--wfo` | `services/wfo_run_service.py` |
| `cli/portfolio.py` | `--portfolio-backtest` | `services/portfolio_run_service.py` |
| `cli/batch.py` | `batch` | `services/batch_run_service.py` |
| `cli/wfo_batch.py` | `wfo-batch` | `services/wfo_batch_run_service.py` |

## Contributor Shortcut

If you are deciding where a change belongs:

- CLI flag parsing or dispatch -> `run.py` or `cli/`
- workflow orchestration -> `services/`
- order simulation, spread rules, or session gating -> `execution/`
- single-strategy event-loop behavior -> `single_asset/`
- allocation, slot coordination, or shared-capital execution -> `portfolio_layer/`
- saved metrics or reports -> `analytics/`
- UI rendering or route handling -> `runtime/terminal_ui/`
- runtime settings -> `config/`
