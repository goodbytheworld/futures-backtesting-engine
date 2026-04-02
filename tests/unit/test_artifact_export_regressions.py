from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest_engine.analytics.exporter import save_backtest_results
from src.backtest_engine.analytics.shared.transforms.stress import _build_trade_cost_series
from src.backtest_engine.config import BacktestSettings
from src.backtest_engine.execution import ExecutionHandler, Order
from src.backtest_engine.portfolio_layer.reporting.results import save_portfolio_results
from src.backtest_engine.services.artifact_service import (
    inspect_result_bundle,
    load_result_bundle_uncached,
)

from ._execution_test_helpers import StubSettings, _bar


def test_slippage_propagates_to_exported_trades_and_daily_cost_series(tmp_path: Path) -> None:
    """Non-zero fill slippage must survive into trade artifacts and daily stress inputs."""
    handler = ExecutionHandler(StubSettings(spread_ticks=1))

    handler.execute_order(Order(symbol="ES", quantity=1, side="BUY"), _bar("2024-01-01 09:30:00", 100.0))
    handler.execute_order(Order(symbol="ES", quantity=1, side="SELL"), _bar("2024-01-01 10:00:00", 101.0))

    settings = BacktestSettings(base_dir=tmp_path, results_dir=Path("results"))
    history = pd.DataFrame(
        {"total_value": [100_000.0, 100_025.0]},
        index=pd.to_datetime(["2024-01-01 09:30:00", "2024-01-01 10:00:00"]),
    )
    save_backtest_results(
        history=history,
        trades=handler.trades,
        report_str="report",
        metrics={"finite": np.float64(1.25), "nan": np.nan, "inf": np.inf},
        settings=settings,
    )

    trades_df = pd.read_parquet(tmp_path / "results" / "trades.parquet")
    metrics = json.loads((tmp_path / "results" / "metrics.json").read_text(encoding="utf-8"))

    assert float(trades_df.loc[0, "slippage"]) == 25.0
    assert metrics["finite"] == 1.25
    assert metrics["nan"] is None
    assert metrics["inf"] is None

    commission_daily, slippage_daily = _build_trade_cost_series(trades_df, {})
    assert float(commission_daily.iloc[0]) == 5.0
    assert float(slippage_daily.iloc[0]) == 25.0


def test_zero_trade_single_results_still_write_trade_artifact(tmp_path: Path) -> None:
    """Single-run exports must write an empty trades artifact so the UI can load zero-trade runs."""
    settings = BacktestSettings(base_dir=tmp_path, results_dir=Path("results"))
    history = pd.DataFrame(
        {"total_value": [100_000.0, 100_000.0]},
        index=pd.to_datetime(["2024-01-01 09:30:00", "2024-01-01 10:00:00"]),
    )

    save_backtest_results(
        history=history,
        trades=[],
        report_str="report",
        metrics={"Total Trades": 0},
        settings=settings,
    )

    results_root = tmp_path / "results"
    trades_df = pd.read_parquet(results_root / "trades.parquet")
    manifest = json.loads((results_root / "manifest.json").read_text(encoding="utf-8"))
    status = inspect_result_bundle(results_dir=str(results_root))
    bundle = load_result_bundle_uncached(results_dir=str(results_root))

    assert trades_df.empty
    assert "trades.parquet" in manifest["artifacts"]
    assert status.state == "valid"
    assert bundle is not None
    assert bundle.trades.empty


def test_portfolio_results_metrics_are_strict_json_and_daily_pnl_is_incremental(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Portfolio artifacts must keep strict JSON and truthful incremental daily PnL semantics."""
    monkeypatch.chdir(tmp_path)

    history = pd.DataFrame(
        {
            "total_value": [1000.0, 1010.0, 1012.0, 1007.0],
            "slot_0_pnl": [0.0, 10.0, 12.0, 7.0],
        },
        index=pd.to_datetime(
            [
                "2024-01-01 10:00:00",
                "2024-01-01 15:00:00",
                "2024-01-02 10:00:00",
                "2024-01-02 15:00:00",
            ]
        ),
    )

    save_portfolio_results(
        history=history,
        exposure_df=pd.DataFrame(),
        slot_trades={},
        report_str="report",
        metrics={"finite": np.float64(2.5), "nan": np.nan, "inf": np.inf},
        slot_names={0: "StrategyA"},
        slot_weights={0: 1.0},
    )

    metrics = json.loads((tmp_path / "results" / "portfolio" / "metrics.json").read_text(encoding="utf-8"))
    strategy_pnl_daily = pd.read_parquet(tmp_path / "results" / "portfolio" / "strategy_pnl_daily.parquet")

    assert metrics["finite"] == 2.5
    assert metrics["nan"] is None
    assert metrics["inf"] is None
    assert strategy_pnl_daily["slot_0_pnl"].tolist() == [10.0, -3.0]


def test_portfolio_results_can_write_to_namespaced_scenario_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Scenario reruns must write to a separate namespace with reconstructible metadata."""
    monkeypatch.chdir(tmp_path)

    history = pd.DataFrame(
        {
            "total_value": [1000.0, 1010.0],
            "slot_0_pnl": [0.0, 10.0],
        },
        index=pd.to_datetime(["2024-01-01 10:00:00", "2024-01-01 15:00:00"]),
    )
    output_dir = tmp_path / "results" / "scenarios" / "scenario-001" / "portfolio"

    saved_dir = save_portfolio_results(
        history=history,
        exposure_df=pd.DataFrame(),
        slot_trades={},
        report_str="report",
        metrics={"finite": 1.0},
        slot_names={0: "StrategyA"},
        slot_weights={0: 1.0},
        output_dir=output_dir,
        manifest_metadata={
            "run_kind": "scenario",
            "scenario_id": "scenario-001",
            "baseline_run_id": "baseline-abc",
            "scenario_type": "costs",
            "scenario_params": {"commission_multiplier": 2.0},
        },
    )

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    marker = (output_dir.parent / ".run_type").read_text(encoding="utf-8").strip()

    assert saved_dir == output_dir
    assert manifest["run_kind"] == "scenario"
    assert manifest["scenario_id"] == "scenario-001"
    assert manifest["baseline_run_id"] == "baseline-abc"
    assert manifest["scenario_type"] == "costs"
    assert manifest["scenario_params"] == {"commission_multiplier": 2.0}
    assert marker == "portfolio"
