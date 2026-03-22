# Architecture Reference

## Layer Map

```text
run.py
  -> cli/
      -> services/
          -> engines
          -> analytics artifact I/O
          -> data access

runtime/terminal_ui/
  -> services/
  -> analytics/shared/
```

## Current Boundaries

### `run.py`

- Parses CLI arguments.
- Dispatches to `cli/`.
- Launches the terminal UI when requested.

### `cli/`

- Thin adapters only.
- `single.py`, `wfo.py`, and `portfolio.py` delegate to `src/backtest_engine/services/`.
- Lightweight batch commands are parsed in `run.py` and dispatched to `cli/batch.py` or `cli/wfo_batch.py`.

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
