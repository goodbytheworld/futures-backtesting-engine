# Architecture Reference

## Layer Map

```text
run.py
  -> cli/
      -> services/
          -> single_asset/
          -> portfolio_layer/
          -> analytics/
          -> data/

runtime/terminal_ui/
  -> services/
  -> analytics/shared/
  -> static/charts_shared.js
```

## Canonical Packages

### `src/backtest_engine/config/`

- Canonical home for runtime settings models.
- Split by bounded concern:
  - `backtest.py` for engine/data/execution/batch settings
  - `terminal_ui.py` for runtime UI settings
  - `scenario.py` for scenario-engine defaults

### `src/backtest_engine/execution/`

- Shared execution kernel.
- Owns `Order`, `Fill`, `Trade`, `ExecutionHandler`, `OrderBook`, spread logic, and time/session controls.
- Used by the single-asset engine directly and by the portfolio engine through bridge semantics.

### `src/backtest_engine/single_asset/`

- Canonical single-strategy, single-primary-symbol event loop.
- Used by standard backtests and walk-forward runs.

### `src/backtest_engine/portfolio_layer/`

- Shared-capital, multi-slot portfolio engine.
- Owns allocation, scheduling, portfolio book, bridge execution flow, and portfolio artifact generation.
- This package is a separate bounded context, not an extension method on the single engine.

### `src/backtest_engine/services/`

- Canonical orchestration layer between CLI/runtime adapters and engines.
- Safe place for artifact lookup, scenario metadata handling, workflow assembly, and run-service composition.

### `src/backtest_engine/analytics/`

- Metrics, reports, artifact exporters, and shared analytics transforms.
- The terminal UI consumes analytics outputs and saved artifacts; it is not the analytics source of truth.

### `src/backtest_engine/runtime/`

- Runtime-facing delivery surfaces.
- `runtime/terminal_ui/` is the active FastAPI analytics runtime for saved artifacts.
- Keep runtime code focused on HTTP, rendering, and dependency composition.

### `src/backtest_engine/optimization/`

- Walk-forward optimization and Optuna orchestration.
- Depends on the single-asset engine and service-layer workflows, not on the terminal UI.

## Import Rules

| Caller | Can Import | Should Not Import |
|---|---|---|
| `run.py`, `cli/` | `services.*`, dashboard launcher helpers | engine internals, analytics implementation details |
| `services/` | engines, analytics exporters, data, config | HTTP handlers, templates, CLI parsing |
| `runtime/terminal_ui/` | `services.*`, `analytics.shared.*`, config | CLI modules, engine event-loop internals |
| engines | config, data, strategies, analytics exporters, execution | HTTP, templates, CLI |

## Artifact Flow

1. A service launches an engine workflow.
2. The engine writes artifacts to disk.
3. `services/artifact_service.py` inspects bundles and loads metadata.
4. `services/paths.py` resolves results roots and scenario paths.
5. The terminal UI loads artifacts through service-layer helpers.

## Important Invariants

- No-lookahead execution: strategy sees `bar[t]`, execution starts on `t + 1`.
- Shared-capital portfolio accounting: total equity is cash plus marked-to-market open exposure.
- Strategy constructor contract is still legacy: strategies receive an engine instance.

## Current Architectural Intent

- We want clean separation, not framework theater.
- Practical shape:
  - strategies / alpha in `src/strategies/`
  - execution and engine physics in `src/backtest_engine/execution/`, `single_asset/`, and `portfolio_layer/`
  - analysis and artifact consumers in `src/backtest_engine/analytics/` and `runtime/`
- Refactors should preserve behavioral contracts first, then improve folder and import clarity.
