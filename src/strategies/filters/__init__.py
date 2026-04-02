"""
Composable strategy filters and signal helpers.

Modules in this package should be named after reusable market concepts rather
than one specific strategy family.
"""

from .candles import CandleMetrics, candle_metrics
from .chart_patterns import DiamondPatternLevels, detect_diamond_patterns
from .core import (
    apply_wfo_dataclass_overrides,
    gate_trade_direction,
    hour_of_day_mask,
    wilder_atr,
)
from .kalman import KalmanBeta
from .market_structure import structure_trend_masks
from .price_levels import RangeLevels, rolling_range_levels
from .stationarity import ADFFilter, HalfLifeFilter
from .trend import TrendFilter
from .volatility import AtrStretchFilter, ShockFilter, VolatilityRegimeFilter
from .volatility_envelopes import EnvelopeBands, bollinger_bands, keltner_channels
from .volume_analysis import rolling_poc_proxy, rolling_volume_ratio

__all__ = [
    "ADFFilter",
    "AtrStretchFilter",
    "CandleMetrics",
    "DiamondPatternLevels",
    "EnvelopeBands",
    "HalfLifeFilter",
    "KalmanBeta",
    "RangeLevels",
    "ShockFilter",
    "TrendFilter",
    "VolatilityRegimeFilter",
    "apply_wfo_dataclass_overrides",
    "bollinger_bands",
    "candle_metrics",
    "detect_diamond_patterns",
    "gate_trade_direction",
    "hour_of_day_mask",
    "keltner_channels",
    "rolling_poc_proxy",
    "rolling_range_levels",
    "rolling_volume_ratio",
    "structure_trend_masks",
    "wilder_atr",
]
