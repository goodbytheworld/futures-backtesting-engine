"""
Price-level helpers.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RangeLevels:
    """
    Prior support/resistance levels from a completed rolling range.

    Args:
        resistance: Prior rolling high.
        support: Prior rolling low.
        height: Prior range height.
    """

    resistance: pd.Series
    support: pd.Series
    height: pd.Series


def rolling_range_levels(
    high: pd.Series,
    low: pd.Series,
    lookback: int,
    shift: int = 1,
) -> RangeLevels:
    """
    Returns prior support/resistance levels from a rolling price range.

    Methodology:
        The levels are shifted by default so strategies compare the current bar
        against a fully completed range and never against a level that already
        includes the breakout bar itself.

    Args:
        high: High-price series.
        low: Low-price series.
        lookback: Rolling window length.
        shift: Number of bars to shift the completed levels.

    Returns:
        RangeLevels with aligned support, resistance, and range height.
    """
    resistance = high.rolling(lookback, min_periods=lookback).max().shift(shift)
    support = low.rolling(lookback, min_periods=lookback).min().shift(shift)
    return RangeLevels(
        resistance=resistance,
        support=support,
        height=resistance - support,
    )
