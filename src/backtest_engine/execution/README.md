# Execution Package

Canonical shared execution-kernel code lives here.

## Modules

| Module | Purpose |
|---|---|
| `__init__.py` | shared `Order`, `Fill`, `Trade`, and `ExecutionHandler` |
| `cost_model.py` | shared order-type execution cost profiles and rough-cost helpers |
| `order_book.py` | resting-order registry for the single-asset engine |
| `spread_model.py` | deterministic spread tick model |
| `time_controls.py` | session gating and trading-hour helpers |

## Notes

- The portfolio engine reuses the shared fill semantics but still owns its own higher-level OMS bridge in `portfolio_layer/`.
- Default retail execution cost profile:
  - `MARKET` and `STOP` use the configured spread model.
  - `LIMIT` and `STOP_LIMIT` default to zero spread slippage unless explicitly overridden.
  - All order types fall back to the shared `commission_rate` unless explicitly overridden.
