"""
Backward-compatible re-export shim.

All scenario job infrastructure now lives in
``src.backtest_engine.services.scenario_job_service``. This module
re-exports every public symbol so existing imports keep working.
"""

from src.backtest_engine.services.scenario_job_service import (  # noqa: F401
    FINAL_SCENARIO_JOB_STATES,
    SUPPORTED_QUEUE_JOB_TYPES,
    Redis,
    RedisError,
    Queue,
    Retry,
    ScenarioJobMetadata,
    ScenarioJobService,
    ScenarioJobStatus,
    ScenarioJobStore,
    TerminalQueueConfig,
    run_portfolio_scenario_job,
    _resolve_redis_bindings,
    _resolve_rq_bindings,
    _scenario_job_id,
    _update_job_metadata,
    _update_job_stage,
    _utc_now_iso,
)

# Re-export domain symbols used by other terminal_ui modules.
from src.backtest_engine.services.artifact_service import (  # noqa: F401
    ResultBundle,
    load_result_bundle_uncached,
)
from src.backtest_engine.services.paths import get_results_dir  # noqa: F401
from src.backtest_engine.services.scenario_runner_service import (  # noqa: F401
    build_stress_scenario_spec,
    get_baseline_run_id,
    run_portfolio_scenario,
)
from src.backtest_engine.analytics.shared.risk_models import StressMultipliers  # noqa: F401
from src.backtest_engine.analytics.scenario_engine import (  # noqa: F401
    ArtifactFamily,
    JobType,
    ProgressStageId,
    ScenarioSpec,
    build_progress_metadata,
    get_progress_stages,
)

__all__ = [
    "FINAL_SCENARIO_JOB_STATES",
    "SUPPORTED_QUEUE_JOB_TYPES",
    "ScenarioJobMetadata",
    "ScenarioJobService",
    "ScenarioJobStatus",
    "ScenarioJobStore",
    "TerminalQueueConfig",
    "run_portfolio_scenario_job",
]
