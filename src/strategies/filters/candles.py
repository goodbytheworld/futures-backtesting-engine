"""
Candle-shape helpers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CandleMetrics:
    """
    Candle body and wick fractions relative to the full bar range.

    Args:
        body_fraction: Absolute body size divided by full range.
        upper_wick_fraction: Upper wick size divided by full range.
        lower_wick_fraction: Lower wick size divided by full range.
    """

    body_fraction: pd.Series
    upper_wick_fraction: pd.Series
    lower_wick_fraction: pd.Series


def candle_metrics(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
) -> CandleMetrics:
    """
    Computes body and wick proportions for signal quality checks.

    Args:
        open_: Open-price series.
        high: High-price series.
        low: Low-price series.
        close: Close-price series.

    Returns:
        CandleMetrics aligned to the bar index.
    """
    full_range = (high - low).abs()
    safe_range = full_range.replace(0.0, np.nan)
    body = (close - open_).abs()
    upper_ref = pd.concat([open_, close], axis=1).max(axis=1)
    lower_ref = pd.concat([open_, close], axis=1).min(axis=1)
    upper_wick = (high - upper_ref).clip(lower=0.0)
    lower_wick = (lower_ref - low).clip(lower=0.0)
    return CandleMetrics(
        body_fraction=(body / safe_range).fillna(0.0),
        upper_wick_fraction=(upper_wick / safe_range).fillna(0.0),
        lower_wick_fraction=(lower_wick / safe_range).fillna(0.0),
    )
