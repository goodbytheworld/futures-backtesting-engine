"""
src/backtest_engine/services/single_run_service.py

Service layer for single-asset backtesting.
"""

from __future__ import annotations

from typing import Any

from src.backtest_engine.engine import BacktestEngine
from src.backtest_engine.services.run_helpers import load_strategy_and_validate_cache


def run_single_backtest(strategy_name: str, settings: Any) -> None:
    """
    Runs a single-asset backtest.

    Args:
        strategy_name: Short strategy name (e.g. 'sma').
        settings: BacktestSettings instance.
    """
    strategy_class = load_strategy_and_validate_cache(strategy_name, settings)

    print("=" * 60)
    print(f"  Backtest: {strategy_class.__name__}")
    print(f"  Symbol   : {settings.default_symbol}")
    print(f"  Timeframe: {settings.low_interval}")
    print(f"  Capital  : ${settings.initial_capital:,.0f}")
    print("=" * 60)

    engine = BacktestEngine(settings=settings)
    engine.run(strategy_class)
    engine.show_results()
