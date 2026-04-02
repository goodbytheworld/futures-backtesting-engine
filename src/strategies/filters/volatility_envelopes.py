"""
Volatility-envelope indicators.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .core import wilder_atr

_EPSILON = 1e-9


@dataclass(frozen=True)
class EnvelopeBands:
    """
    Volatility envelope with absolute and normalized width.

    Args:
        middle: Rolling mean / EMA center line.
        upper: Upper envelope bound.
        lower: Lower envelope bound.
        width: Absolute band width.
        normalized_width: Width scaled by the absolute center line.
    """

    middle: pd.Series
    upper: pd.Series
    lower: pd.Series
    width: pd.Series
    normalized_width: pd.Series


def bollinger_bands(
    close: pd.Series,
    window: int,
    num_std: float,
) -> EnvelopeBands:
    """
    Builds Bollinger Bands with normalized width.

    Args:
        close: Close-price series.
        window: Rolling mean / standard deviation window.
        num_std: Standard-deviation multiplier.

    Returns:
        EnvelopeBands object aligned to ``close``.
    """
    rolling_mean = close.rolling(window=window, min_periods=window).mean()
    rolling_std = close.rolling(window=window, min_periods=window).std()
    upper = rolling_mean + rolling_std * float(num_std)
    lower = rolling_mean - rolling_std * float(num_std)
    width = upper - lower
    normalized_width = width / rolling_mean.abs().clip(lower=_EPSILON)
    return EnvelopeBands(
        middle=rolling_mean,
        upper=upper,
        lower=lower,
        width=width,
        normalized_width=normalized_width,
    )


def keltner_channels(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    ema_window: int,
    atr_window: int,
    atr_mult: float,
) -> EnvelopeBands:
    """
    Builds Keltner Channels around an EMA baseline.

    Args:
        high: High-price series.
        low: Low-price series.
        close: Close-price series.
        ema_window: EMA span for the center line.
        atr_window: ATR span for the channel width.
        atr_mult: ATR multiplier for the upper/lower bands.

    Returns:
        EnvelopeBands object aligned to the input index.
    """
    middle = close.ewm(span=ema_window, adjust=False).mean()
    atr = wilder_atr(high=high, low=low, close=close, span=atr_window)
    upper = middle + atr * float(atr_mult)
    lower = middle - atr * float(atr_mult)
    width = upper - lower
    normalized_width = width / middle.abs().clip(lower=_EPSILON)
    return EnvelopeBands(
        middle=middle,
        upper=upper,
        lower=lower,
        width=width,
        normalized_width=normalized_width,
    )
