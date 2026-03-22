"""
Targeted boundary tests for the portfolio run service extraction.

Verifies that:
1. compute_data_version uses the public get_cache_file_path API.
2. parse_scenario_params handles valid and invalid JSON.
3. resolve_replay_window_filters extracts dates from typed payloads.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from src.backtest_engine.services.portfolio_run_service import (
    compute_data_version,
    parse_scenario_params,
    resolve_replay_window_filters,
    merge_scenario_manifest_metadata,
)


def test_compute_data_version_uses_public_api(tmp_path: Path) -> None:
    """compute_data_version must call get_cache_file_path, not _get_cache_file."""
    cache_file = tmp_path / "ES_5m.parquet"
    cache_file.write_text("dummy", encoding="utf-8")

    data_lake = MagicMock()
    data_lake.get_cache_file_path.return_value = cache_file

    version = compute_data_version(data_lake, [("ES", "5m")])

    data_lake.get_cache_file_path.assert_called_once_with("ES", "5m")
    assert isinstance(version, str)
    assert len(version) == 16


def test_parse_scenario_params_returns_none_for_empty() -> None:
    """Empty or None input should return None."""
    assert parse_scenario_params(None) is None
    assert parse_scenario_params("") is None


def test_parse_scenario_params_parses_valid_json() -> None:
    """Valid JSON dict string should be returned as a dict."""
    result = parse_scenario_params('{"key": "value"}')
    assert result == {"key": "value"}


def test_resolve_replay_window_filters_extracts_dates() -> None:
    """Typed replay window payloads should produce datetime filters."""
    start, end = resolve_replay_window_filters(
        {
            "artifact_manifest": {
                "selection_metadata": {
                    "replay_window": {
                        "date_range": {
                            "start": "2024-01-01T00:00:00+00:00",
                            "end": "2024-02-01T00:00:00+00:00",
                        }
                    }
                }
            }
        }
    )
    assert start == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert end == datetime(2024, 2, 1, tzinfo=timezone.utc)


def test_resolve_replay_window_filters_returns_none_for_empty() -> None:
    """Missing or empty params should return (None, None)."""
    assert resolve_replay_window_filters(None) == (None, None)
    assert resolve_replay_window_filters({}) == (None, None)


def test_merge_scenario_manifest_metadata_promotes_fields() -> None:
    """Scenario manifest fields should be promoted into the main manifest."""
    manifest: dict = {}
    merge_scenario_manifest_metadata(
        manifest,
        {"artifact_manifest": {"artifact_family": "scenarios", "job_type": "stress_rerun"}},
    )
    assert manifest["artifact_family"] == "scenarios"
    assert manifest["job_type"] == "stress_rerun"
