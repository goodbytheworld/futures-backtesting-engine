"""
cli/single.py

Single-asset backtest CLI handler.

Responsibility: Parse strategy name and run single-asset backtest service.
Called by run.py --backtest.
"""

from __future__ import annotations

from typing import Any

from src.backtest_engine.services.single_run_service import run_single_backtest


def run(strategy_name: str, settings: Any) -> None:
    """
    Runs a single-asset backtest.

    Args:
        strategy_name: Short strategy name (e.g. 'sma').
        settings: BacktestSettings instance.
    """
    run_single_backtest(strategy_name, settings)
