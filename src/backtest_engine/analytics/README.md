# Analytics Module

This package owns post-run analytics, artifact export, and reusable transforms consumed by the terminal UI and tests.

## Main Modules

| Module | Purpose |
|---|---|
| `core.py` | `PerformanceMetrics` facade over metrics, trade stats, and report formatting |
| `metrics.py` | equity-curve performance calculations |
| `trades.py` | trade-level statistics and derived KPIs |
| `exit_analysis.py` | post-run exit enrichment such as MAE, MFE, and timing fields |
| `report.py` | terminal-facing report formatting |
| `exporter.py` | canonical artifact writer for single-engine runs |
| `artifact_contract.py` | artifact compatibility and metadata helpers |

## Shared Analytics

`shared/` contains pure transforms and risk models that can be reused by:

- terminal UI routes/builders
- tests
- future analytics consumers

Keep logic here pure when possible.

## Scenario Engine

`scenario_engine/` contains scenario-related contracts, manifests, and progress helpers used by rerun workflows.

## Runtime Relationship

The active UI is not inside this package anymore.

- UI code lives in `src/backtest_engine/runtime/terminal_ui/`
- analytics code lives here

If a change is about metrics, artifact structure, or analytics semantics, it belongs here. If it is about FastAPI routes, templates, or rendering payload assembly, it belongs in `runtime/terminal_ui/`.
