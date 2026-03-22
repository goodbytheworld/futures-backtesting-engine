"""
Runtime service composition — creates and wires all shared service instances.

Methodology:
    Extracted from app.py so the factory function focuses purely on FastAPI
    route registration and template mounting, while lifecycle/queue wiring
    is assembled here and passed in as composed services.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI

from src.backtest_engine.services.scenario_job_service import ScenarioJobService
from src.backtest_engine.services.worker_manager import LocalRedisManager, LocalWorkerManager
from src.backtest_engine.runtime.terminal_ui.service import load_terminal_runtime_context


class RuntimeServices:
    """Container for all runtime-scoped service instances.

    Methodology:
        A plain data-holder that avoids scattered module-level globals while
        still being lightweight (no DI framework).  The lifespan handler can
        reference this single object rather than closing over many locals.
    """

    __slots__ = (
        "runtime",
        "worker_manager",
        "redis_manager",
        "job_service",
    )

    def __init__(
        self,
        *,
        runtime: object,
        worker_manager: LocalWorkerManager,
        redis_manager: Optional[LocalRedisManager],
        job_service: ScenarioJobService,
    ) -> None:
        self.runtime = runtime
        self.worker_manager = worker_manager
        self.redis_manager = redis_manager
        self.job_service = job_service


def _parse_local_redis_url(redis_url: Optional[str]) -> Optional[tuple[str, int]]:
    """Extracts host and port from a redis URL, returning None for remote URLs.

    Methodology:
        Only localhost/127.0.0.1/::1 qualify as local.  Remote URLs are left
        to the user's own infrastructure; the managed redis button is hidden.
    """
    if not redis_url:
        return None
    try:
        parsed = urlparse(redis_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 6379
        if host not in {"localhost", "127.0.0.1", "::1"}:
            return None
        return host, port
    except Exception:
        return None


def compose_runtime_services(
    *,
    results_dir: Optional[str] = None,
    project_root: Path,
) -> RuntimeServices:
    """Creates all runtime service instances for a single dashboard lifecycle.

    Args:
        results_dir: Optional results root override (tests inject tmp dirs).
        project_root: Repository root for worker/redis subprocess paths.

    Returns:
        A ``RuntimeServices`` container wired and ready for the app factory.
    """
    runtime = load_terminal_runtime_context()
    worker_manager = LocalWorkerManager(
        config=runtime.queue_config,
        results_dir=results_dir,
        project_root=project_root,
    )
    local_redis_coords = _parse_local_redis_url(runtime.queue_config.redis_url)
    redis_manager: Optional[LocalRedisManager] = None
    if local_redis_coords is not None:
        redis_manager = LocalRedisManager(
            host=local_redis_coords[0],
            port=local_redis_coords[1],
            results_dir=results_dir,
            project_root=project_root,
        )
    job_service = ScenarioJobService(
        results_dir=results_dir,
        config=runtime.queue_config,
        worker_manager=worker_manager,
        redis_manager=redis_manager,
    )
    return RuntimeServices(
        runtime=runtime,
        worker_manager=worker_manager,
        redis_manager=redis_manager,
        job_service=job_service,
    )


def build_lifespan(services: RuntimeServices):
    """Returns an async lifespan context manager that shuts down managed processes.

    Args:
        services: The composed runtime services to tear down on exit.
    """

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        """Stops the managed worker and redis-server when the dashboard process exits."""
        try:
            yield
        finally:
            try:
                services.worker_manager.stop_worker()
            except Exception:
                pass
            if services.redis_manager is not None:
                try:
                    services.redis_manager.stop_redis()
                except Exception:
                    pass

    return _lifespan
