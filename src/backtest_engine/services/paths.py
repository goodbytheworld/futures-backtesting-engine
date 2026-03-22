"""
Framework-neutral path resolution for the backtesting project.

Methodology:
    Path discovery lives in a neutral service module so FastAPI, Streamlit,
    tests, CLI handlers, and async workers can all share the same artifact
    root logic without importing UI code.
"""

from __future__ import annotations

from pathlib import Path


def get_project_root() -> Path:
    """
    Resolves the repository root from the services package location.

    Returns:
        Absolute path to the repository root.
    """
    return Path(__file__).resolve().parents[3]


def get_results_dir() -> Path:
    """
    Resolves the shared results directory under the project root.

    Returns:
        Absolute path to ``results/``.
    """
    return get_project_root() / "results"


def get_scenarios_root(create: bool = True) -> Path:
    """
    Resolves the scenario artifact namespace under ``results/scenarios/``.

    Args:
        create: Whether to create the directory when it does not exist.

    Returns:
        Absolute path to the scenario root.
    """
    root = get_results_dir() / "scenarios"
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root
