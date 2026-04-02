"""
Chart-pattern detectors.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

_EPSILON = 1e-9


@dataclass(frozen=True)
class DiamondPatternLevels:
    """
    Rolling diamond-top / diamond-bottom structure estimates.

    Args:
        top_pattern: ``True`` when a completed diamond top is detected.
        bottom_pattern: ``True`` when a completed diamond bottom is detected.
        upper_boundary: Upper bound of the contracting half of the pattern.
        lower_boundary: Lower bound of the contracting half of the pattern.
        height: Full pattern height.
    """

    top_pattern: pd.Series
    bottom_pattern: pd.Series
    upper_boundary: pd.Series
    lower_boundary: pd.Series
    height: pd.Series


def detect_diamond_patterns(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr: pd.Series,
    window: int,
    trend_window: int,
    min_slope_atr_ratio: float = 0.15,
    max_contraction_ratio: float = 0.75,
    min_height_atr: float = 2.5,
) -> DiamondPatternLevels:
    """
    Detects practical diamond-top / diamond-bottom structures.

    Methodology:
        A diamond is approximated as an expanding first half followed by a
        contracting second half. The prior trend classifies the structure as a
        top or bottom candidate. This is intentionally heuristic, but reusable
        beyond breakout-only strategies.

    Args:
        high: High-price series.
        low: Low-price series.
        close: Close-price series.
        atr: ATR series used for scale normalization.
        window: Total bars in the rolling diamond pattern.
        trend_window: Bars used to classify the prior trend.
        min_slope_atr_ratio: Minimum slope magnitude in ATR terms.
        max_contraction_ratio: Max width ratio of contracting half vs expanding half.
        min_height_atr: Minimum total pattern height in ATR units.

    Returns:
        DiamondPatternLevels aligned to the input index.
    """
    pattern_window = max(8, int(window))
    first_half = max(4, pattern_window // 2)

    hi = high.to_numpy(dtype=np.float64)
    lo = low.to_numpy(dtype=np.float64)
    cl = close.to_numpy(dtype=np.float64)
    atr_values = atr.to_numpy(dtype=np.float64)
    n = len(close)

    top_pattern = np.zeros(n, dtype=bool)
    bottom_pattern = np.zeros(n, dtype=bool)
    upper_boundary = np.full(n, np.nan, dtype=np.float64)
    lower_boundary = np.full(n, np.nan, dtype=np.float64)
    height = np.full(n, np.nan, dtype=np.float64)

    for pos in range(pattern_window - 1, n):
        start = pos - pattern_window + 1
        midpoint = start + first_half
        expanding_high = hi[start:midpoint]
        expanding_low = lo[start:midpoint]
        contracting_high = hi[midpoint : pos + 1]
        contracting_low = lo[midpoint : pos + 1]
        current_atr = atr_values[pos]

        if (
            expanding_high.size < 4
            or contracting_high.size < 4
            or not np.isfinite(current_atr)
            or current_atr <= 0.0
        ):
            continue

        first_width = np.nanmax(expanding_high) - np.nanmin(expanding_low)
        second_width = np.nanmax(contracting_high) - np.nanmin(contracting_low)
        full_height = np.nanmax(hi[start : pos + 1]) - np.nanmin(lo[start : pos + 1])
        slope_threshold = current_atr * float(min_slope_atr_ratio) / max(first_half, 1)

        upper_boundary[pos] = np.nanmax(contracting_high)
        lower_boundary[pos] = np.nanmin(contracting_low)
        height[pos] = full_height

        expansion_ok = (
            _ols_slope(expanding_high) > slope_threshold
            and _ols_slope(expanding_low) < -slope_threshold
        )
        contraction_ok = (
            _ols_slope(contracting_high) < -slope_threshold
            and _ols_slope(contracting_low) > slope_threshold
            and second_width <= first_width * float(max_contraction_ratio)
        )
        size_ok = full_height >= current_atr * float(min_height_atr)
        if not (expansion_ok and contraction_ok and size_ok):
            continue

        trend_start = max(0, start - int(trend_window))
        trend_slice = cl[trend_start:start]
        if trend_slice.size < max(4, int(trend_window) // 2):
            continue

        trend_slope = _ols_slope(trend_slice)
        if trend_slope > slope_threshold * 0.5:
            top_pattern[pos] = True
        elif trend_slope < -slope_threshold * 0.5:
            bottom_pattern[pos] = True

    return DiamondPatternLevels(
        top_pattern=pd.Series(top_pattern, index=close.index),
        bottom_pattern=pd.Series(bottom_pattern, index=close.index),
        upper_boundary=pd.Series(upper_boundary, index=close.index),
        lower_boundary=pd.Series(lower_boundary, index=close.index),
        height=pd.Series(height, index=close.index),
    )


def _ols_slope(values: np.ndarray) -> float:
    """
    Returns a simple OLS slope for equally spaced observations.

    Args:
        values: One-dimensional numeric array.

    Returns:
        Slope coefficient.
    """
    if values.size < 2:
        return 0.0
    x = np.arange(values.size, dtype=np.float64)
    x_centered = x - x.mean()
    y_centered = values - values.mean()
    denominator = float(np.dot(x_centered, x_centered))
    if denominator <= _EPSILON:
        return 0.0
    return float(np.dot(x_centered, y_centered) / denominator)
