"""
Composable strategy filters and signal helpers.

This package keeps the historical public API from ``src.strategies.filters``
while splitting implementations by responsibility so strategies and LLM tools
can open smaller, topic-focused modules.
"""

from .core import (
    apply_wfo_dataclass_overrides,
    gate_trade_direction,
    hour_of_day_mask,
    wilder_atr,
)
from .kalman import KalmanBeta
from .stationarity import ADFFilter, HalfLifeFilter
from .trend import TrendFilter
from .volatility import AtrStretchFilter, ShockFilter, VolatilityRegimeFilter

__all__ = [
    "ADFFilter",
    "AtrStretchFilter",
    "HalfLifeFilter",
    "KalmanBeta",
    "ShockFilter",
    "TrendFilter",
    "VolatilityRegimeFilter",
    "apply_wfo_dataclass_overrides",
    "gate_trade_direction",
    "hour_of_day_mask",
    "wilder_atr",
]
