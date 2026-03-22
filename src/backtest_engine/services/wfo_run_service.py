"""
src/backtest_engine/services/wfo_run_service.py

Service layer for Walk-Forward Optimization runs.
"""

from __future__ import annotations

from typing import Any

from src.backtest_engine.optimization.wfv_optimizer import WalkForwardOptimizer
from src.backtest_engine.services.run_helpers import load_strategy_and_validate_cache


def run_wfo_backtest(strategy_name: str, settings: Any) -> None:
    """
    Runs Walk-Forward Validation for the given strategy.

    Args:
        strategy_name: Short strategy name (e.g. 'sma').
        settings: BacktestSettings instance.
    """
    strategy_class = load_strategy_and_validate_cache(strategy_name, settings)

    print("=" * 60)
    print(f"  WFV: {strategy_class.__name__}")
    print(f"  Symbol   : {settings.default_symbol}")
    print(f"  Timeframe: {settings.low_interval}")
    print("=" * 60)

    wfv = WalkForwardOptimizer(settings=settings)
    wfv.run(strategy_class=strategy_class)
