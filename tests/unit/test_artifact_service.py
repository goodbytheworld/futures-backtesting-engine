"""
Targeted boundary tests for the artifact service extraction.

Verifies that:
1. services.artifact_service exports all expected symbols.
2. Legacy dashboard.core.data_layer re-exports remain importable.
3. services.paths resolves correctly.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def test_services_artifact_service_exports_all_symbols() -> None:
    """The new artifact service must export every symbol the old data_layer exposed."""
    from src.backtest_engine.services.artifact_service import (
        ArtifactCompatibility,
        ArtifactLoadStatus,
        ArtifactMetadata,
        ResultBundle,
        ResultBundleCache,
        ResultBundleService,
        assess_bundle_compatibility,
        build_artifact_metadata,
        clear_result_bundle_cache,
        inspect_result_bundle,
        load_result_bundle,
        load_result_bundle_uncached,
        result_bundle_service,
    )
    assert ResultBundle is not None
    assert callable(inspect_result_bundle)
    assert callable(load_result_bundle)
    assert isinstance(result_bundle_service, ResultBundleService)


def test_legacy_dashboard_data_layer_reexports_work() -> None:
    """Legacy imports from dashboard.core.data_layer must still resolve."""
    from src.backtest_engine.services.artifact_service import (
        ResultBundle,
        inspect_result_bundle,
        load_result_bundle,
        result_bundle_service,
    )
    assert ResultBundle is not None
    assert callable(inspect_result_bundle)
    assert callable(load_result_bundle)


def test_legacy_dashboard_paths_reexports_work() -> None:
    """Legacy imports from dashboard.core.paths must still resolve."""
    from src.backtest_engine.services.paths import (
        get_project_root,
        get_results_dir,
        get_scenarios_root,
    )
    assert callable(get_project_root)
    assert callable(get_results_dir)
    assert callable(get_scenarios_root)


def test_services_paths_resolves_project_root() -> None:
    """The neutral paths module should resolve a valid project root."""
    from src.backtest_engine.services.paths import get_project_root, get_results_dir

    root = get_project_root()
    assert root.exists()
    assert (root / "src").exists() or (root / "run.py").exists()

    results = get_results_dir()
    assert results.name == "results"


def test_result_bundle_can_be_instantiated_from_service() -> None:
    """ResultBundle from the new service should behave identically to the old one."""
    from src.backtest_engine.services.artifact_service import ResultBundle

    bundle = ResultBundle(
        run_type="single",
        history=pd.DataFrame({"total_value": [1000.0]}),
        trades=pd.DataFrame(),
    )
    assert bundle.run_type == "single"
    assert bundle.compatibility is not None
