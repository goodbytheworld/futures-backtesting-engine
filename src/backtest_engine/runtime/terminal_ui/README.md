# Terminal UI Runtime

This package contains the active FastAPI analytics interface for saved backtest artifacts.

## Responsibilities

- load the latest result bundle or an explicitly selected artifact root
- render terminal-style HTML partials and charts
- expose operational endpoints for scenario jobs, Redis, and worker lifecycle
- host the Stress Testing tab for queue-driven reruns

## Main Modules

| Module | Purpose |
|---|---|
| `app.py` | FastAPI app factory |
| `composition.py` | dependency wiring and startup composition |
| `service.py` | runtime-facing artifact and shell data access |
| `routes_partials.py` | HTML partial routes |
| `routes_charts.py` | chart payload routes |
| `routes_operations.py` | stress-testing and operational routes |
| `jobs.py` | compatibility re-export shim for scenario job infrastructure |
| `worker_manager.py` | managed local worker lifecycle helpers |
| `windows_worker.py` | Windows-specific worker helpers |

## Tabs

Current bottom-panel surface includes:

- PnL Distribution
- Strategy Stats
- Risk
- Stress Testing
- Exit Analysis
- Operations

Portfolio artifacts also expose Decomposition and Correlations.

## Stress Testing Status

What exists now:

- dedicated `Stress Testing` tab
- Redis/RQ-backed queue integration
- managed local Redis and worker controls
- queueable execution-shock reruns for portfolio artifacts
- durable job metadata and SSE progress updates

What is not done yet:

- full frontend for Monte Carlo and simulation families
- public queue surface for market replay, tail-event reruns, or simulation jobs
- rich scenario-family launcher beyond execution-shock reruns

## Relationship To Other Packages

- artifact loading and scenario orchestration are delegated to `src/backtest_engine/services/`
- reusable analytics logic should live in `src/backtest_engine/analytics/`
- this package should stay focused on HTTP, rendering, and runtime composition
