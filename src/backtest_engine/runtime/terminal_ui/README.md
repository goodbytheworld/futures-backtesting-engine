# Terminal UI Runtime

This package contains the active FastAPI analytics interface for saved backtest artifacts.

## Purpose

The terminal UI is a delivery surface, not the source of truth for engine logic.

It should:

- load saved artifacts
- assemble terminal-style HTML partials and chart payloads
- expose operational endpoints for scenario jobs, Redis, and worker lifecycle
- host the Stress Testing tab for queue-driven reruns

It should not:

- own backtest execution semantics
- duplicate analytics transforms that already belong in `analytics/`
- accumulate workflow orchestration that belongs in `services/`

## Main Modules

| Module | Purpose |
|---|---|
| `app.py` | FastAPI app factory |
| `composition.py` | dependency wiring and startup composition |
| `service.py` | runtime-facing artifact and shell data access |
| `routes_partials.py` | HTML partial routes |
| `routes_charts.py` | chart payload routes |
| `routes_operations.py` | stress-testing and operational routes |
| `static/charts_shared.js` | shared chart helpers and request lifecycle utilities |
| `static/charts_renderers_*.js` | grouped renderer implementations for chart families |
| `static/charts.js` | chart dispatcher and DOM wiring for runtime refreshes |
| `static/terminal.css` | stylesheet manifest that loads terminal UI style modules |
| `jobs.py` | runtime facade for scenario job infrastructure |
| `worker_manager.py` | managed local worker lifecycle helpers |
| `windows_worker.py` | Windows-specific worker helpers |

## Contributor Rules

- keep `routes_*.py` thin
- put reusable analytics math in `src/backtest_engine/analytics/`
- put artifact and scenario orchestration in `src/backtest_engine/services/`
- keep this package focused on HTTP, rendering, and runtime composition

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

What is intentionally still missing:

- full frontend for Monte Carlo and simulation families
- public queue surface for market replay, tail-event reruns, or simulation jobs
- rich scenario-family launchers beyond execution-shock reruns

## Related Packages

- artifact loading and scenario orchestration are delegated to `src/backtest_engine/services/`
- reusable analytics logic lives in `src/backtest_engine/analytics/`
- runtime-wide packaging notes live in `src/backtest_engine/runtime/README.md`
