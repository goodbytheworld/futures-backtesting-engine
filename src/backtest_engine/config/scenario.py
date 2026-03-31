"""
Scenario engine settings models.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScenarioEngineSettings(BaseModel):
    """
    Settings for the backend scenario foundation.
    """

    scenario_contract_version: str = Field(
        default="scenario-spec.v1",
        description="Version tag written into typed scenario contracts and job metadata.",
    )
    scenario_artifact_version: str = Field(
        default="1.0",
        description="Manifest version for scenario and simulation artifact contracts.",
    )
    default_replay_window_days: int = Field(
        default=63,
        description="Default replay window length in calendar days when a manual window is not supplied.",
    )
    max_candidate_replay_windows: int = Field(
        default=12,
        description="Upper bound reserved for future replay-window ranking candidates.",
    )
    queue_retention_days: int = Field(
        default=14,
        description="Default retention policy for durable file-backed scenario job metadata.",
    )
    simulation_seed_default: int = Field(
        default=42,
        description="Default seed reserved for future simulation-family execution.",
    )
    artifact_retention_days: int = Field(
        default=30,
        description="Default retention horizon for scenario and simulation artifacts.",
    )
    default_latency_ms: int = Field(
        default=0,
        description="Execution latency placeholder for current scenario contracts.",
    )
