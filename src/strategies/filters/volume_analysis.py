"""
Volume-analysis helpers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def rolling_volume_ratio(
    volume: pd.Series,
    window: int,
) -> pd.Series:
    """
    Normalizes current volume by its rolling average.

    Args:
        volume: Volume series.
        window: Rolling average window.

    Returns:
        Volume ratio series where ``1.0`` means average volume.
    """
    baseline = volume.rolling(window=window, min_periods=window).mean()
    return volume / baseline.replace(0.0, np.nan)


def rolling_poc_proxy(
    close: pd.Series,
    volume: pd.Series,
    window: int,
) -> pd.Series:
    """
    Approximates a rolling point-of-control using volume-weighted closing price.

    Methodology:
        A true price-by-volume profile requires bins. For intraday strategy
        gating we use a rolling VWAP-style proxy that still captures whether
        volume concentration is migrating upward or downward inside the range.

    Args:
        close: Close-price series.
        volume: Volume series.
        window: Rolling aggregation window.

    Returns:
        Rolling volume-weighted price proxy.
    """
    weighted_price = (close * volume).rolling(window=window, min_periods=window).sum()
    volume_sum = volume.rolling(window=window, min_periods=window).sum()
    return weighted_price / volume_sum.replace(0.0, np.nan)
