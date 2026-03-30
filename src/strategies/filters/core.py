"""
Shared indicator and configuration helpers for strategies.

These helpers are intentionally lightweight and dependency-free beyond
NumPy/Pandas so multiple strategies can reuse them without pulling in the
heavier statistical filter implementations.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np
import pandas as pd


def apply_wfo_dataclass_overrides(engine: Any, cfg: Any, prefix: str) -> None:
    """
    Merges optional walk-forward trial overrides into a config dataclass.

    Methodology:
        WFO injects strategy-specific keys into ``engine.settings`` using the
        ``{prefix}_{field_name}`` convention. Strategies can keep one local
        config dataclass and let this helper selectively override only fields
        that were optimized for the current trial.

    Args:
        engine: Strategy engine exposing a ``settings`` object.
        cfg: Dataclass instance to mutate in place.
        prefix: Prefix used by the strategy's WFO parameter namespace.
    """
    for field in dataclasses.fields(cfg):
        wfo_key = f"{prefix}_{field.name}"
        if hasattr(engine.settings, wfo_key):
            setattr(cfg, field.name, getattr(engine.settings, wfo_key))


def wilder_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    span: int,
) -> pd.Series:
    """
    Calculates Average True Range using Wilder-style exponential smoothing.

    Methodology:
        True range is the bar-wise maximum of intrabar range, distance from the
        previous close to the current high, and distance from the previous
        close to the current low. The resulting series is smoothed with
        ``ewm(..., adjust=False)`` to match the ATR convention used across the
        strategy layer.

    Args:
        high: High-price series.
        low: Low-price series.
        close: Close-price series.
        span: ATR smoothing span.

    Returns:
        ATR series aligned to the input index.
    """
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(span=span, adjust=False).mean()


def hour_of_day_mask(
    index: pd.Index,
    start_h: int,
    end_h: int,
    enabled: bool,
) -> np.ndarray:
    """
    Builds a boolean session mask from whole-hour boundaries.

    Methodology:
        The mask accepts bars in ``[start_h, end_h)``. When ``start_h > end_h``,
        the window wraps midnight, allowing overnight sessions without manual
        date splitting.

    Args:
        index: Timestamp index to evaluate.
        start_h: Inclusive session start hour.
        end_h: Exclusive session end hour.
        enabled: When ``False``, all bars are allowed.

    Returns:
        NumPy boolean mask aligned to ``index``.
    """
    if not enabled:
        return np.ones(len(index), dtype=bool)
    dt_index = pd.DatetimeIndex(pd.to_datetime(index, utc=False))
    hours = dt_index.hour.to_numpy()
    if start_h <= end_h:
        return (hours >= start_h) & (hours < end_h)
    return (hours >= start_h) | (hours < end_h)


def gate_trade_direction(
    trade_direction: str,
    long_ok: bool,
    short_ok: bool,
) -> tuple[bool, bool]:
    """
    Applies a long/short direction gate to precomputed entry permissions.

    Args:
        trade_direction: ``both``, ``long``, or ``short``.
        long_ok: Ungated long-entry eligibility.
        short_ok: Ungated short-entry eligibility.

    Returns:
        Tuple of gated ``(long_ok, short_ok)`` flags.
    """
    direction = (trade_direction or "both").strip().lower()
    if direction == "long":
        return long_ok, False
    if direction == "short":
        return False, short_ok
    return long_ok, short_ok
