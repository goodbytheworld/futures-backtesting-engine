# Architecture Reference

## Layer Map

```
CLI (cli/)
  └─→ Services (src/backtest_engine/services/)
       ├─→ Engines (src/backtest_engine/, portfolio_layer/)
       ├─→ Data (src/data/)
       └─→ Artifact I/O (services/artifact_service, services/paths)

Server Runtime (runtime/terminal_ui/)
  └─→ Services (services/*)
       └─→ Shared Analytics (analytics/shared/transforms/, risk_models)
```

## Terminal UI Runtime

- **`runtime/terminal_ui/`** — canonical server runtime.
- **`composition.py`** — handles service and lifecycle wiring.
- **`app.py`** — application factory that contains request parsing helpers, error rendering logic, and shell handlers (not just a route registry).

## Access Rules

| Caller Layer | Can Import | Cannot Import |
|---|---|---|
| CLI (`cli/`) | `services.*`, `settings`, `runtime.*` | Engine internals, private methods, `analytics.*` |
| Services | `engines`, `data`, `settings`, `artifact_contract` | CLI, HTTP, dashboard UI, `runtime.*` |
| Terminal UI Runtime | `services.*`, `analytics.shared.transforms`, `analytics.shared.risk_models` | CLI, engine internals |
| Engines | `settings`, `data`, `strategies` | HTTP, CLI, analytics UI |

## Engine Roles

- **BacktestEngine** — single-asset, bar-by-bar execution with position tracking.
- **PortfolioBacktestEngine** — multi-slot orchestrator using `LegacyStrategyAdapter` to bridge the `BaseStrategy(engine)` constructor contract.
- **WFO (Walk-Forward)** — parameter optimization wrapper around `BacktestEngine`.

## Strategy Contract

The current API is a **legacy contract**:

```python
class BaseStrategy(ABC):
    def __init__(self, engine: BacktestEngine): ...
```

Strategies receive the full engine object. The portfolio layer provides a `_MockEngine` shim.
Future direction: replace engine injection with a narrower `StrategyContext` interface.
No mass migration in this iteration — the legacy contract is documented, not deprecated.

## Artifact Flow

1. Engine writes artifacts to `results/` (via `exporter.py` or `portfolio_layer/reporting/`).
2. `services/artifact_service.py` inspects and loads bundles from disk.
3. `services/paths.py` resolves the project root, results dir, and scenario root.
4. Terminal UI and tests import directly from `services.*`.

## What Stays Legacy

- `BaseStrategy(engine)` constructor contract — documented, not changed.
