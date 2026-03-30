"""
Cached-data validation helpers for the CLI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from src.backtest_engine.settings import BacktestSettings


def run_data_validation(
    *,
    settings: "BacktestSettings",
    symbols: Sequence[str],
    timeframes: Sequence[str] | None,
) -> None:
    """
    Validates cached OHLCV datasets and prints the report.

    Args:
        settings: Shared runtime settings with cache-path configuration.
        symbols: Optional symbol filters parsed from the CLI.
        timeframes: Optional timeframe filters parsed from the CLI.
    """
    from src.data import DataValidator

    validator = DataValidator()
    cache_dir = settings.get_cache_path()
    requested_symbols = [
        str(symbol).strip().upper()
        for symbol in symbols
        if str(symbol).strip()
    ]
    requested_timeframes = list(timeframes or [])

    print("=" * 60)
    if requested_symbols:
        print(f"  Validating cached data for: {requested_symbols}")
    else:
        print(f"  Validating all cached data in: {cache_dir}")
    if requested_timeframes:
        print(f"  Timeframes: {requested_timeframes}")
    print("=" * 60)

    results = []
    if requested_symbols:
        for symbol in requested_symbols:
            results.extend(
                validator.validate_cache_directory(
                    cache_dir=cache_dir,
                    symbol=symbol,
                    timeframes=requested_timeframes,
                )
            )
    else:
        results = validator.validate_cache_directory(
            cache_dir=cache_dir,
            symbol=None,
            timeframes=requested_timeframes,
        )

    print(validator.generate_report(results))
