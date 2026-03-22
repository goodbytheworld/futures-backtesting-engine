"""
cli/portfolio.py

Portfolio backtest CLI handler.

Responsibility: Parse CLI arguments and delegate to the portfolio run service.
This module is called exclusively by run.py --portfolio-backtest.
"""

from __future__ import annotations

from typing import Optional

from src.backtest_engine.services.portfolio_run_service import run_portfolio_backtest


def run(
    config_path: str,
    results_subdir: Optional[str] = None,
    scenario_id: Optional[str] = None,
    baseline_run_id: Optional[str] = None,
    scenario_type: Optional[str] = None,
    scenario_params_json: Optional[str] = None,
) -> None:
    """
    Thin CLI adapter for the portfolio backtest use-case.

    Methodology:
        All orchestration lives in ``portfolio_run_service``.  This module
        only exists to satisfy the CLI dispatch contract in ``run.py``.

    Args:
        config_path: Path to the YAML config file (absolute or project-relative).
        results_subdir: Optional project-relative or absolute artifact directory.
        scenario_id: Optional scenario identifier for manifest metadata.
        baseline_run_id: Optional baseline reference for scenario manifests.
        scenario_type: Optional scenario classification stored in manifest metadata.
        scenario_params_json: Optional JSON payload describing rerun parameters.
    """
    run_portfolio_backtest(
        config_path=config_path,
        results_subdir=results_subdir,
        scenario_id=scenario_id,
        baseline_run_id=baseline_run_id,
        scenario_type=scenario_type,
        scenario_params_json=scenario_params_json,
    )
