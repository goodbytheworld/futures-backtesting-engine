# Architecture Reference

## Layer Map

```text
run.py
  -> cli/main_parser.py
  -> cli/lightweight_batch.py
  -> cli/runtime_dashboard.py
  -> cli/data_validation.py
  -> cli/
      -> services/
          -> engines
          -> analytics artifact I/O
          -> data access

runtime/terminal_ui/
  -> services/
  -> analytics/shared/
  -> static/charts_shared.js
```

## Current Boundaries

### `run.py`

- Thin entry point only.
- Delegates parser construction to `cli/main_parser.py`.
- Delegates positional batch parsing to `cli/lightweight_batch.py`.
- Delegates dashboard launching to `cli/runtime_dashboard.py`.
- Delegates cache validation flow to `cli/data_validation.py`.

### `cli/`

- Thin adapters only.
- `single.py`, `wfo.py`, and `portfolio.py` delegate to `src/backtest_engine/services/`.
- Lightweight batch commands are parsed in `run.py` and dispatched to `cli/batch.py` or `cli/wfo_batch.py`.
- `main_parser.py` owns main argparse setup and single-run overrides.
- `lightweight_batch.py` owns positional `batch` / `wfo-batch` parsing.
- `runtime_dashboard.py` owns dashboard port resolution and launch mechanics.
- `data_validation.py` owns cache validation reporting.

### `src/backtest_engine/services/`

- Canonical orchestration layer.
- Handles cache validation, scenario metadata, artifact lookup, and use-case assembly.
- Safe place for shared workflow code used by CLI and terminal UI.

### Engines

- `src/backtest_engine/engine.py`
  - `BacktestEngine`
  - Single-asset event loop
  - Used by standard backtests and WFO runs

- `src/backtest_engine/portfolio_layer/engine/engine.py`
  - `PortfolioBacktestEngine`
  - Portfolio event loop with shared capital and slot-level execution
  - Used by portfolio runs and scenario reruns

### `src/backtest_engine/analytics/`

- Metrics, reports, artifact exporters, and shared analytics transforms.
- `analytics/shared/` contains reusable pure transforms and risk models.
- The terminal UI consumes analytics outputs and saved artifacts; it is not the analytics source of truth.

### `src/backtest_engine/runtime/terminal_ui/`

- Active FastAPI runtime.
- `app.py` builds the app.
- `composition.py` wires dependencies and runtime lifecycle.
- `routes_*.py` contain HTTP handlers.
- `service.py` handles artifact loading and runtime-facing queries.
- `chart_builders.py`, `risk_builders.py`, and `table_builders.py` build pure payloads for rendering.
- `exit_charts/` contains topic-specific exit-analysis payload builders behind `exit_chart_builders.py`.
- `static/charts_shared.js` holds common chart loading, resize, and axis utilities.

### Strategy Filters

- `src/strategies/filters/` is the reusable filter package for strategies.
- Keep the package split by concern: core helpers, volatility, trend, stationarity, Kalman.
- Preserve `from src.strategies.filters import ...` compatibility when extending it.

### Optimization

- `optimization/optimizer.py` owns Optuna trial execution and slice evaluation.
- `optimization/wfv_optimizer.py` owns fold orchestration.
- `optimization/wfv_report.py` owns fold/report models and human-readable reporting.
- `optimization/optuna_runtime.py` owns optional Optuna import/runtime helpers.

### Worker Lifecycle

- `services/worker_manager.py` is a compatibility facade.
- `services/worker_management/worker_manager.py` owns local RQ worker lifecycle.
- `services/worker_management/redis_manager.py` owns local Redis lifecycle.

## Import Rules

| Caller | Can Import | Should Not Import |
|---|---|---|
| `run.py`, `cli/` | `services.*`, `settings`, dashboard launcher helpers | engine internals, analytics implementation details |
| `services/` | engines, data, settings, artifact helpers | HTTP handlers, Jinja templates, CLI parsing |
| `runtime/terminal_ui/` | `services.*`, `analytics.shared.*` | CLI modules, engine internals |
| engines | settings, data, strategies, analytics exporters | HTTP, CLI, terminal UI |

## Artifact Flow

1. An engine run writes artifacts to disk.
2. `services/artifact_service.py` inspects bundles and loads metadata.
3. `services/paths.py` resolves results roots and scenario paths.
4. Terminal UI routes and tests consume those service-layer helpers.

## Important Invariants

- No-lookahead execution: signal at `close[t]`, fill at `open[t+1]`.
- Portfolio accounting: total equity is cash plus marked-to-market open exposure.
- Strategy contract is still legacy: strategies receive an engine instance.

## Legacy That Still Matters

- `BaseStrategy(engine)` remains the active strategy constructor contract.
- Portfolio mode still uses compatibility adapters for single-engine strategies.
- That contract is documented here because contributors are likely to touch it accidentally.
