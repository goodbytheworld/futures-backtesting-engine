# Execution Contract

This document defines the shared execution-kernel semantics for the backtest engines.

## Scope

The scope of this contract is intentionally limited:

- deterministic market, limit, stop, and stop-limit order simulation
- gap-aware bar-based fills
- deterministic same-bar conflict handling
- no partial fills
- no bid/ask replay
- no TWAP/VWAP execution

Portfolio orchestration remains unchanged in this iteration. The shared execution
layer is extended without changing the portfolio engine event loop structure.

## Layer Responsibilities

- Signal/Alpha: strategies generate trade intent
- Portfolio Construction: allocator converts intent into target exposure
- Execution/OMS: converts deltas into concrete orders and manages resting orders
- Broker/Simulator: simulates fills, fees, slippage, and gap behavior

The current repository still contains legacy strategy contracts, so the engines
bridge into this model incrementally.

## Portfolio Engine Notes

The portfolio engine shares the same fill semantics but remains target-driven:

- strategies emit directional signals
- the allocator converts those signals into target exposure
- the engine queues delta orders against current position and pending quantity
- reduce-only protective exits are supported for live positions
- lower-timeframe replay is optional and used only for protective same-bar stop/target conflicts

The portfolio path still preserves its own event-loop contract and shared-capital accounting rules, which are summarized in `src/backtest_engine/portfolio_layer/README.md`.

## Order Model

The shared order object supports:

- `id`
- `symbol`
- `side`
- `quantity`
- `order_type`: `MARKET`, `LIMIT`, `STOP`, `STOP_LIMIT`
- `limit_price`
- `stop_price`
- `time_in_force`: `GTC`, `DAY`, `IOC`
- `timestamp`
- `placed_at`
- `status`
- `reduce_only`

Status transitions (single-engine path with `OrderBook`):

- `NEW` on construction; on submit to the book, `NEW -> SUBMITTED`
- when the execution handler processes the order, `NEW|SUBMITTED -> ACCEPTED`
- `ACCEPTED -> FILLED`
- `ACCEPTED -> CANCELLED` (including IOC not filled, DAY expiry, EOD cancel)
- validation failures before acceptance: `REJECTED` (order not accepted for fill simulation)

This iteration does not implement a repository-wide OMS yet.
The single engine now uses a dedicated `OrderBook` as its resting-order registry.
Portfolio mode remains on the legacy orchestration path for now.

## Core Timing Invariant

- strategy observes bar `t`
- generated orders become eligible on bar `t + 1`
- no order may use future bars to decide whether it should have filled

## Fill Rules

### Market Orders

- next eligible bar open by default
- current bar close only for explicit `execute_at_close=True` paths on orders
  that were already pending before the current bar
- fresh bar `t` orders never get promoted into same-bar EOD execution; they are
  cancelled if forced EOD handling occurs before bar `t + 1`

### Limit Orders

Buy limit:

- if `open <= limit`, fill immediately at `open`
- else if `low <= limit`, fill at `limit`

Sell limit:

- if `open >= limit`, fill immediately at `open`
- else if `high >= limit`, fill at `limit`

### Stop Orders

Buy stop:

- if `open >= stop`, fill immediately at `open`
- else if `high >= stop`, fill at `stop`

Sell stop:

- if `open <= stop`, fill immediately at `open`
- else if `low <= stop`, fill at `stop`

### Stop-Limit Orders

Stop-limit orders are supported deterministically with conservative bar logic:

- the stop condition must trigger first at the bar open or inside the bar
- after triggering, the limit condition must also be marketable on the same bar
- if the bar only proves that both prices were touched but not the order of
  touches, the simulator uses the conservative assumption and requires the limit
  condition to be explicitly satisfied by the bar range

## Default Execution Cost Assumptions

The repository uses a simple retail-style default execution cost profile:

- `MARKET` and `STOP` use the configured spread model
- `LIMIT` and `STOP_LIMIT` default to zero spread slippage unless explicitly
  overridden
- all order types fall back to the shared base `commission_rate` unless
  `commission_rate_by_order_type` provides an exact override

This default stays intentionally simple:

- no bid/ask replay
- no maker rebates
- no queue-priority uncertainty

## Gap-Aware Rules

Gap-aware behavior is mandatory for stop and limit realism:

- long stop at `95`, next open at `90` -> fill at `90` adjusted by slippage
- buy limit at `100`, next open at `98` -> fill at `98` with no default spread
  slippage

The simulator never gives a synthetic fill at the stale trigger price when the
market has already moved through it by the next available open.

## Intra-Bar Ambiguity

Default policy: `pessimistic`.

If a coarse OHLC bar proves that both a favorable exit and a protective stop
were reachable but cannot prove ordering, the engine must choose the worst
equity outcome. For a long position this means the stop wins; for a short
position this also means the stop wins.

The repository can load `1m` data, but this iteration does not auto-load lower
timeframe data inside the simulator by default. In portfolio mode, lower-
timeframe replay for protective OCO stop/target conflicts is an explicit
opt-in path controlled by `intrabar_conflict_resolution=lower_timeframe` plus
`intrabar_resolution_timeframe`. If lower-TF data is missing or incomplete, the
simulator must fall back to the pessimistic coarse-bar policy. Pessimistic
resolution remains the default because it has lower implementation risk and
lower lookahead risk.

## Session and Liquidation Priority

- risk liquidation has priority over normal orders
- forced EOD liquidation has priority over resting non-market orders
- forced EOD handling may execute only orders that were already pending before
  the current bar
- non-market resting orders are cancelled before forced EOD liquidation in the
  single engine

## Partial Fills

Partial fills are explicitly out of scope for this iteration.

## Cancel/Replace

This iteration supports cancel by terminal state only:

- `IOC` cancels if not filled on the first eligible bar
- `DAY` can persist intraday but is cancelled at forced EOD handling
- `GTC` persists across eligible bars until fill or explicit cancellation path

Order replacement is not implemented yet.
