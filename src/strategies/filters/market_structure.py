"""
Market-structure helpers.
"""

from __future__ import annotations

import pandas as pd


def structure_trend_masks(
    low: pd.Series,
    high: pd.Series,
    window: int,
) -> tuple[pd.Series, pd.Series]:
    """
    Approximates higher-lows / lower-highs structure inside a range.

    Args:
        low: Low-price series.
        high: High-price series.
        window: Rolling swing window.

    Returns:
        Tuple ``(higher_lows, lower_highs)`` aligned to the input index.
    """
    lookback = max(2, int(window))
    step = max(1, lookback // 2)
    swing_low = low.rolling(lookback, min_periods=lookback).min().shift(1)
    swing_high = high.rolling(lookback, min_periods=lookback).max().shift(1)
    higher_lows = (swing_low > swing_low.shift(step)).fillna(False)
    lower_highs = (swing_high < swing_high.shift(step)).fillna(False)
    return higher_lows, lower_highs
