from __future__ import annotations

import json

import pandas as pd

import src.backtest_engine.services.scenario_runner_service as scenario_runner
from src.backtest_engine.services.artifact_service import ResultBundle


def test_list_portfolio_scenarios_reads_namespaced_manifests(tmp_path, monkeypatch) -> None:
    """Scenario discovery should find namespaced portfolio manifests and sort newest first."""
    results_root = tmp_path / "results"
    scenarios_root = results_root / "scenarios"
    first_manifest = scenarios_root / "scenario-a" / "portfolio" / "manifest.json"
    second_manifest = scenarios_root / "scenario-b" / "portfolio" / "manifest.json"
    first_manifest.parent.mkdir(parents=True, exist_ok=True)
    second_manifest.parent.mkdir(parents=True, exist_ok=True)
    first_manifest.write_text(
        json.dumps({"scenario_id": "scenario-a", "generated_at": "2026-03-14T01:00:00+00:00"}),
        encoding="utf-8",
    )
    second_manifest.write_text(
        json.dumps({"scenario_id": "scenario-b", "generated_at": "2026-03-14T02:00:00+00:00"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(scenario_runner, "get_results_dir", lambda: results_root)

    scenarios = scenario_runner.list_portfolio_scenarios()

    assert [item["manifest"]["scenario_id"] for item in scenarios] == ["scenario-b", "scenario-a"]


def test_list_portfolio_scenarios_supports_legacy_root_manifest_layout(tmp_path, monkeypatch) -> None:
    """Scenario discovery should remain compatible with the earlier root-manifest layout."""
    results_root = tmp_path / "results"
    scenarios_root = results_root / "scenarios"
    legacy_manifest = scenarios_root / "scenario-legacy" / "manifest.json"
    legacy_manifest.parent.mkdir(parents=True, exist_ok=True)
    legacy_manifest.write_text(
        json.dumps(
            {
                "scenario_id": "scenario-legacy",
                "generated_at": "2026-03-14T03:00:00+00:00",
                "baseline_run_id": "baseline-123",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(scenario_runner, "get_results_dir", lambda: results_root)

    scenarios = scenario_runner.list_portfolio_scenarios()

    assert scenarios[0]["manifest"]["scenario_id"] == "scenario-legacy"


def test_scenario_matches_baseline_requires_explicit_reference() -> None:
    """Scenario comparison must reject bundles that do not reference the active baseline."""
    empty_history = pd.DataFrame({"total_value": []})
    empty_trades = pd.DataFrame()
    baseline_bundle = ResultBundle(
        run_type="portfolio",
        history=empty_history,
        trades=empty_trades,
        manifest={"generated_at": "baseline-123"},
    )
    matching_scenario = ResultBundle(
        run_type="portfolio",
        history=empty_history,
        trades=empty_trades,
        manifest={"baseline_run_id": "baseline-123"},
    )
    mismatched_scenario = ResultBundle(
        run_type="portfolio",
        history=empty_history,
        trades=empty_trades,
        manifest={"baseline_run_id": "other-baseline"},
    )

    assert scenario_runner.scenario_matches_baseline(baseline_bundle, matching_scenario)
    assert not scenario_runner.scenario_matches_baseline(baseline_bundle, mismatched_scenario)
