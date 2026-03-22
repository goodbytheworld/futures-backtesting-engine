"""
Backward-compatible re-export shim.

All worker and Redis lifecycle management now lives in
``src.backtest_engine.services.worker_manager``. This module
re-exports every public symbol so existing imports keep working.
"""

from src.backtest_engine.services.worker_manager import (  # noqa: F401
    LocalRedisManager,
    LocalWorkerManager,
    ManagedRedisSnapshot,
    ManagedWorkerSnapshot,
    RedisLifecycleState,
    WorkerLifecycleState,
)

__all__ = [
    "LocalRedisManager",
    "LocalWorkerManager",
    "ManagedRedisSnapshot",
    "ManagedWorkerSnapshot",
    "RedisLifecycleState",
    "WorkerLifecycleState",
]
