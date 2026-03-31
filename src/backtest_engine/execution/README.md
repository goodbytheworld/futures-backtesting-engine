# Execution Package

Canonical shared execution-kernel code lives here.

## Modules

| Module | Purpose |
|---|---|
| `__init__.py` | shared `Order`, `Fill`, `Trade`, and `ExecutionHandler` |
| `order_book.py` | resting-order registry for the single-asset engine |
| `spread_model.py` | deterministic spread tick model |
| `time_controls.py` | session gating and trading-hour helpers |

## Notes

- The portfolio engine reuses the shared fill semantics but still owns its own higher-level OMS bridge in `portfolio_layer/`.
