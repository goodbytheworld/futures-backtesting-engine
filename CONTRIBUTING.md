# Contributing Guide

This project is structured for research accuracy first. Contributions should preserve the execution contract, keep module boundaries clear, and avoid hidden behavior changes.

## First Read

Before changing code, read:

1. [`README.md`](README.md)
2. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
3. [`docs/MODULE_MAP.md`](docs/MODULE_MAP.md)
4. [`docs/agents.md`](docs/agents.md)

If `dev_context/` exists locally, [`dev_context/CLEAN_CODE_MCP.md`](dev_context/CLEAN_CODE_MCP.md) is a useful internal reference, but it is not required for external contributors.

## Local Setup

```bash
git clone https://github.com/DanRedelien/futures-backtesting-engine.git
cd futures-backtesting-engine
pip install -r requirements.txt
pytest tests/
```

Python `3.11+` is recommended.

If you need scenario queueing from the terminal UI, install Redis separately.

## Main Workflows

```bash
# single backtest
python run.py --backtest --strategy sma --symbol ES --tf 1h

# walk-forward optimization
python run.py --wfo --strategy zscore --symbol ES --tf 1h

# portfolio backtest
python run.py --portfolio-backtest

# lightweight batch backtests
python run.py batch --strategies sma zscore --symbol ES NQ --tf 1h 30m

# lightweight WFO batch sweep
python run.py wfo-batch --strategies sma zscore --symbol ES --tf 1h

# terminal UI
python run.py --dashboard
```

## Development Flow

1. Make the smallest coherent change.
2. Keep CLI modules thin; orchestration belongs in `src/backtest_engine/services/`.
3. Keep analytics builders pure when possible.
4. Add or update tests for behavior changes.
5. Update documentation when module boundaries or usage change.

## Architecture Rules

### Layering

- `run.py` parses arguments and dispatches.
- `cli/` adapts CLI flags into service calls.
- `src/backtest_engine/services/` owns use-case orchestration.
- engines execute backtests.
- `runtime/terminal_ui/` serves analytics and operational endpoints.

### Engine Split

There are two different engine entry points and they should not be conflated:

- `src/backtest_engine/engine.py`
  - `BacktestEngine`
  - Single-asset bar-by-bar event loop
  - Owns one portfolio object, one strategy instance, and one instrument stream
  - Used by single-run backtests and as the execution core under WFO

- `src/backtest_engine/portfolio_layer/engine/engine.py`
  - `PortfolioBacktestEngine`
  - Multi-strategy, multi-symbol portfolio event loop
  - Owns shared capital, target allocation, slot-level execution handlers, and unified timeline orchestration
  - Used by portfolio backtests and scenario reruns

Use the single engine when the task is about one strategy on one symbol. Use the portfolio engine when the task depends on slot coordination, rebalancing, shared equity, or portfolio reporting.

### No-Lookahead Invariant

The most important invariant in this repository:

- strategy sees `bar[t]`
- signal is produced from information available at `t`
- order fills at `open[t+1]`

Do not add shifts or data access patterns that violate this.

## Adding A Strategy

1. Add the implementation in `src/strategies/`.
2. Inherit from `BaseStrategy`.
3. Precompute indicators in `__init__`.
4. Keep `on_bar()` lightweight and O(1) per bar.
5. Expose `get_search_space()` if the strategy supports optimization.
6. Register the strategy in `src/strategies/registry.py`.
7. Add tests if the behavior is novel or fragile.

See [`src/strategies/README.md`](src/strategies/README.md) for the detailed contract.

## Adding Or Changing Analytics

- Pure metrics and transforms belong in `src/backtest_engine/analytics/`.
- UI payload builders belong in `src/backtest_engine/runtime/terminal_ui/`.
- Route handlers should stay thin and delegate to services/builders.
- If artifact structure changes, update loaders, tests, and docs together.

Batch-specific note:

- `batch` and `wfo-batch` are intentionally lightweight paths.
- They coordinate many independent scenarios and render Matplotlib summaries instead of writing the full dashboard artifact flow for every run.

## Running Tests

```bash
pytest tests/
pytest tests/unit/
pytest tests/regression/
pytest tests/unit/test_engine_regressions.py
```

At minimum, run the most relevant tests for the area you changed.

## Documentation Expectations

Update docs when you change:

- public CLI behavior
- module ownership or imports
- artifact paths or contracts
- strategy registration flow
- terminal UI routing or runtime composition

For open-source hygiene, prefer updating the closest README or doc instead of adding a new spec file unless the topic spans multiple packages.

## Pull Requests

Good PRs in this repository usually have:

- one focused behavioral goal
- matching tests or a clear reason tests were not added
- doc updates if public behavior changed
- explicit mention of any artifact-contract change

## Keep It Lean

Avoid overengineering. Favor:

- thin adapters
- explicit data flow
- pure helpers over deep abstractions
- docs that explain the real workflow, not hypothetical future layers

If a new concept only matters in one module, document it close to that module instead of creating another top-level document.
