"""
Framework-neutral worker and Redis process lifecycle management.

This module preserves the public import surface while delegating the actual
implementations to smaller worker-management submodules.
"""

from .worker_management.redis_manager import (
    LocalRedisManager,
    ManagedRedisSnapshot,
    RedisLifecycleState,
)
from .worker_management.worker_manager import (
    LocalWorkerManager,
    ManagedWorkerSnapshot,
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
