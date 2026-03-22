# Strategy Development Guide

This package contains concrete trading strategies and the registry that exposes them to the rest of the system.

## Contract

All strategies:

- inherit from `BaseStrategy`
- receive an engine instance in `__init__`
- precompute expensive indicators up front
- keep `on_bar()` lightweight

## Execution Timing

Do not manually shift signals to "fix" timing.

The engine contract is already:

- strategy evaluates `bar[t]`
- returned orders execute at `open[t+1]`

Adding extra `shift(1)` logic usually creates a delayed strategy, not a safer one.

## Adding A Strategy

1. Create a new module in `src/strategies/`.
2. Implement a config object if the strategy has parameters.
3. Precompute indicators in `__init__`.
4. Implement `on_bar()` using O(1) lookups.
5. Implement `get_search_space()` if WFO support is needed.
6. Register the strategy in `registry.py`.

## Registry

`registry.py` is the source of truth for:

- CLI strategy IDs
- accepted aliases
- class loading for portfolio YAML configs

If the strategy is not registered, it is not part of the platform.

## Design Guidance

- keep data slicing out of `on_bar()`
- keep comments and docstrings in English
- put reusable execution settings in `src/backtest_engine/settings.py`
- add tests for unusual entry, exit, or stateful behavior
