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

import pandas as pd

from src.backtest_engine.services.portfolio_run_service import (
    compute_data_version,
    run_portfolio_backtest,
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


def test_run_portfolio_backtest_loads_duty_cycle_and_weight_expansion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """YAML loader should propagate duty_cycle and max_weight_expansion into config."""
    captured: dict = {}
    cache_file = tmp_path / "ES_30m.parquet"
    cache_file.write_text("cache", encoding="utf-8")
    config_path = tmp_path / "portfolio.yaml"
    config_path.write_text(
        "\n".join(
            [
                "portfolio:",
                "  rebalance_frequency: intrabar",
                "  target_portfolio_vol: 0.20",
                "  vol_lookback_bars: 15",
                "  max_weight_expansion: 9.0",
                "strategies:",
                "  - strategy: sma_pullback",
                "    symbols: [ES]",
                "    weight: 1.0",
                "    duty_cycle: 0.25",
            ]
        ),
        encoding="utf-8",
    )

    class DummySettings:
        initial_capital = 100_000.0
        spread_mode = "static"
        spread_ticks = 0.0
        max_cache_staleness_days = 30

    class DummyDataLake:
        def __init__(self, settings) -> None:
            self.settings = settings

        def validate_cache_requirements(self, requirements):
            return []

        def get_cache_file_path(self, symbol, timeframe):
            return cache_file

        def load(self, symbol, timeframe="30m"):
            return pd.DataFrame()

    class DummyEngine:
        def __init__(self, config, settings, start_date=None, end_date=None) -> None:
            captured["config"] = config

        def run(self) -> None:
            captured["ran"] = True

        def show_results(self, benchmark=None, output_dir=None, manifest_metadata=None) -> None:
            captured["manifest_metadata"] = manifest_metadata or {}

    class DummyStrategy:
        pass

    monkeypatch.setattr(
        "src.backtest_engine.portfolio_layer.engine.PortfolioBacktestEngine",
        DummyEngine,
    )
    monkeypatch.setattr(
        "src.strategies.registry.get_strategy_class_by_name",
        lambda name: DummyStrategy,
    )
    monkeypatch.setattr(
        "src.backtest_engine.settings.BacktestSettings",
        DummySettings,
    )
    monkeypatch.setattr(
        "src.data.data_lake.DataLake",
        DummyDataLake,
    )

    run_portfolio_backtest(str(config_path))

    config = captured["config"]
    assert captured["ran"] is True
    assert config.max_weight_expansion == 9.0
    assert config.slots[0].expected_duty_cycle == 0.25
