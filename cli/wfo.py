"""
cli/wfo.py

Walk-Forward Optimization CLI handler.

Responsibility: Parse strategy name, run WFO service.
Called by run.py --wfo.
"""

from __future__ import annotations

from typing import Any

from src.backtest_engine.services.wfo_run_service import run_wfo_backtest


def run(strategy_name: str, settings: Any) -> None:
    """
    Runs Walk-Forward Validation for the given strategy.

    Args:
        strategy_name: Short strategy name.
        settings: BacktestSettings instance.
    """
    run_wfo_backtest(strategy_name, settings)
