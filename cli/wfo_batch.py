"""
cli/wfo_batch.py

Lightweight WFO batch CLI handler.

Responsibility:
    Receives already-parsed CLI values from ``run.py`` and delegates the real
    orchestration to ``wfo_batch_run_service``.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from src.backtest_engine.services.wfo_batch_run_service import run_wfo_batch_backtests


def run(
    strategy_names: Sequence[str],
    symbols: Sequence[str],
    timeframes: Sequence[str],
    settings: Any,
    max_workers: Optional[int] = None,
) -> None:
    """
    Runs the lightweight WFO batch workflow.

    Args:
        strategy_names: Strategy identifiers or aliases.
        symbols: One or many futures symbols.
        timeframes: One or many timeframe strings.
        settings: BacktestSettings instance.
        max_workers: Optional worker override.
    """
    run_wfo_batch_backtests(
        strategy_names=strategy_names,
        symbols=symbols,
        timeframes=timeframes,
        settings=settings,
        max_workers=max_workers,
    )
