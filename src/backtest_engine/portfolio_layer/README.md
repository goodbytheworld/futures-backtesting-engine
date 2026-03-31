# Portfolio Layer

This package implements the multi-strategy portfolio backtest engine.

It is responsible for:

- shared-capital accounting
- slot-level strategy execution
- rebalancing cadence
- target allocation
- portfolio artifact generation

## Subpackages

| Package | Purpose |
|---|---|
| `domain/` | portfolio config, signals, target contracts, policy enums |
| `adapters/` | legacy strategy compatibility for `BaseStrategy(engine)` |
| `scheduling/` | rebalance timing rules |
| `allocation/` | signal-to-target sizing |
| `execution/` | slot runners and portfolio ledger |
| `engine/` | `PortfolioBacktestEngine` event loop |
| `reporting/` | portfolio artifact serialization |

## Important Distinction

This package is not a thin wrapper around the single-asset engine.

- `src/backtest_engine/single_asset/engine.py` runs one strategy against one primary symbol.
- `portfolio_layer/engine/engine.py` runs many strategy slots against a unified timeline with one shared equity pool.

Changes related to allocation, scheduler behavior, portfolio book accounting, slot orchestration, or cross-slot artifacts belong here.

## Execution Model

The portfolio engine is still target-driven:

- strategies emit `StrategySignal`
- the allocator converts signals into `TargetPosition`
- the engine computes delta orders against current position plus pending quantity
- the shared execution kernel handles fill pricing, slippage, commissions, and order-type semantics

Event-loop ordering is behavioral, not cosmetic:

1. fill pending orders
2. mark to market
3. evaluate risk limits
4. collect signals
5. compute targets
6. queue delta orders
7. apply forced EOD handling
8. snapshot portfolio state

Protective reduce-only stop/target exits are supported for live positions. If one coarse bar can prove both protective paths, the default policy remains pessimistic unless lower-timeframe replay is explicitly enabled and complete.

## Volatility Targeting & Position Sizing

The allocator uses a static volatility-targeting methodology. Each strategy slot receives a standalone risk budget scaled by its assigned `weight`.
To compensate for strategies that are out of the market (flat) for significant periods, the engine uses **Static Duty-Cycle Normalization**.

Key concepts and parameters (found in `portfolio_config_example.yaml`):

1. **`target_portfolio_vol`**: The theoretical annualized volatility target for the entire portfolio (e.g., `0.25` for 25%). The engine aims to realize this volatility over the long term.
2. **`weight`**: The proportion of the `target_portfolio_vol` assigned to a specific slot. (e.g. `0.20`). *Note: Weights are aggregated using the `sqrt(weight)` assumption from Modern Portfolio Theory (assumes zero cross-slot correlation).*
3. **`duty_cycle`**: An ex-ante parameter (profiling required) defined as the expected squared normalized exposure: `E[(position / max_position)^2]`. If a strategy is in the market 25% of the time, its theoretical risk budget is expanded by `1 / sqrt(0.25) = 2x` when it *is* in the market, ensuring its long-term volatility contribution matches its `weight`.
4. **`max_weight_expansion`**: A portoflio-level safeguard that caps the duty-cycle multiplier. `max_weight_expansion: 4.0` limits the position multiplier to `sqrt(4.0) = 2.0x`. This prevents extreme leverage for ultra-low duty-cycle strategies.
5. **`rebalance_frequency`**: (`intrabar` | `daily` | `weekly`) Controls how often the allocator snapshots total equity for computing risk budgets.
6. **`max_contracts_per_slot`**: An optional absolute hard cap on the number of contracts a slot can hold, acting as a final fail-safe after volatility sizing and margin-capacity gating.

## Output Contract

- baseline portfolio runs write to `results/portfolio/`
- scenario reruns write to `results/scenarios/<scenario_id>/portfolio/`
- bundles are consumed through `src/backtest_engine/services/artifact_service.py` and the terminal UI

## How to Configure `duty_cycle`

To correctly set the `duty_cycle` for a strategy slot, you must profile its expected market exposure ex-ante. 

**How to find it:**
1. Configure your portfolio with the target strategy and set its `duty_cycle: 1.0` (to disable scaling during the profiling run).
2. Run a representative backtest.
3. Open the Terminal UI dashboard (`--dashboard`) and navigate to the **Decomposition** tab.
4. Look at the **Strategy Decomposition** table and find the **Obs. Duty Cycle** column for your strategy. 
5. Update your `portfolio_config.yaml` with this computed value.
