# Agent Context

Compact project context for LLMs and automation agents working in this repository.

## Mission

This repository is a research-oriented futures backtesting platform with three main workflows:

- single-strategy backtests
- walk-forward optimization
- portfolio backtests with shared capital

The active analytics UI is the FastAPI terminal UI in `src/backtest_engine/runtime/terminal_ui/`.

## Start Here

Read these first:

1. `README.md`
2. `docs/ARCHITECTURE.md`
3. `docs/MODULE_MAP.md`

Read `USAGE.md` only when the task touches CLI help text, command examples, or onboarding docs.

If `dev_context/` exists locally, `dev_context/CLEAN_CODE_MCP.md` is an optional internal reference.
Do not read unrelated files in `dev_context/` unless the task explicitly requires them.

## Non-Negotiable Invariants

### Execution timing

- strategy observes `bar[t]`
- generated orders fill at `open[t+1]`
- do not introduce lookahead through manual shifts or future-index access

### Layering

- `run.py` parses args
- `run.py` stays thin and delegates parser/runtime helpers into `cli/`
- `cli/` adapts args to services
- `services/` orchestrates use cases
- engines execute bar-by-bar logic
- `runtime/terminal_ui/` serves artifacts and analytics views

### Settings

- canonical shared runtime configuration lives in `src/backtest_engine/config/`
- do not scatter new magic numbers through engines or services

## Engine Split

There are two different engines:

### `src/backtest_engine/single_asset/engine.py`

- `BacktestEngine`
- single strategy, single primary symbol
- used by standard backtests and by WFO

### `src/backtest_engine/portfolio_layer/engine/engine.py`

- `PortfolioBacktestEngine`
- multiple slots, multiple symbols, shared capital, allocator, scheduler, portfolio book
- used by portfolio runs and scenario reruns

If a change depends on allocation, rebalancing, slot coordination, or unified timelines, it belongs in the portfolio layer, not in the single engine.

## Active Runtime

The active UI/runtime is `src/backtest_engine/runtime/terminal_ui/`.

Rules:

- `service.py` is the runtime-facing data and artifact layer
- `routes_*.py` stay thin
- builders return payloads, not app-level orchestration
- templates and static assets are terminal UI specific
- shared chart/request helpers live in `static/charts_shared.js`

Do not reintroduce legacy dashboard assumptions into docs or code.

## Strategy Contract

Canonical strategy IDs and aliases live in `src/strategies/registry.py`; only strategies registered there are exposed to the CLI and portfolio YAML loaders.

Strategies still follow a legacy contract:

```python
class BaseStrategy:
    def __init__(self, engine): ...
```

Implications:

- indicators should be precomputed in `__init__`
- `on_bar()` should stay lightweight
- portfolio mode uses adapters to support this contract
- reusable strategy filters live under `src/strategies/filters/`

## Where To Put Changes

- new CLI mode or CLI adapter behavior -> `run.py`, `cli/`
- CLI examples / help text / onboarding commands -> `USAGE.md`, `cli/main_parser.py`
- reusable workflow logic -> `src/backtest_engine/services/`
- execution semantics -> `src/backtest_engine/execution/`, `single_asset/`, or `portfolio_layer/`
- artifacts, metrics, report serialization -> `src/backtest_engine/analytics/`
- strategy implementations -> `src/strategies/`
- UI payloads or routes -> `src/backtest_engine/runtime/terminal_ui/`
- cross-cutting repo docs -> `README.md`, `CONTRIBUTING.md`, `docs/`

## Change Discipline

- Prefer small, local changes.
- Add tests when behavior changes.
- Update nearby docs when public behavior or module ownership changes.
- Keep comments and docs in English.
- Avoid speculative abstractions.

## Useful Local References

- `src/backtest_engine/config/README.md`
- `src/backtest_engine/execution/README.md`
- `src/backtest_engine/single_asset/README.md`
- `src/backtest_engine/analytics/README.md`
- `src/backtest_engine/optimization/README.md`
- `src/backtest_engine/portfolio_layer/README.md`
- `src/backtest_engine/runtime/README.md`
- `tests/README.md`
- `USAGE.md`
