"""
src/backtest_engine/services/run_helpers.py

Common helpers for single backtest and WFO runs.
"""

from __future__ import annotations

import sys
from typing import Any, Iterable, Tuple

from src.data.data_lake import DataLake
from src.strategies.registry import load_strategy_by_id


def validate_cache_requirements_or_exit(
    requirements: Iterable[Tuple[str, str]],
    settings: Any,
) -> None:
    """
    Validates cache freshness for one or many scenario requirements.

    Methodology:
        Lightweight orchestration commands should fail fast before any worker
        process starts.  The helper centralizes the cache contract so single,
        WFO, and batch entry points report the same actionable message.

    Args:
        requirements: Iterable of ``(symbol, timeframe)`` pairs.
        settings: BacktestSettings instance.
    """
    requirement_list = list(requirements)
    data_lake = DataLake(settings)
    cache_errors = data_lake.validate_cache_requirements(requirements=requirement_list)
    if cache_errors:
        print("[Data] Cache freshness check failed:")
        for err in cache_errors:
            print(f"  - {err}")
        print(
            f"[Data] Update cache first. "
            f"Max allowed age: {settings.max_cache_staleness_days} days."
        )
        symbols = sorted({symbol for symbol, _ in requirement_list})
        print(f"[Data] Example: python run.py --download {' '.join(symbols)}")
        sys.exit(1)


def load_strategy_and_validate_cache(strategy_name: str, settings: Any) -> Any:
    """
    Loads strategy from central registry and validates required data cache.
    Exits the process on failure.
    """
    try:
        strategy_class = load_strategy_by_id(strategy_name)
    except ValueError as e:
        print(f"[Error] {e}")
        sys.exit(1)

    validate_cache_requirements_or_exit(
        requirements=[(settings.default_symbol, settings.low_interval)],
        settings=settings,
    )
    return strategy_class
