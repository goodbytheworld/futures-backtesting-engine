"""
Pure payload builders for exit-analysis charts.

This module preserves the public import surface while delegating the actual
builders to smaller topic-focused submodules.
"""

from .exit_charts.decay import build_exit_pnl_decay_payload
from .exit_charts.holding import build_exit_holding_time_payload
from .exit_charts.reasons import (
    build_exit_reason_breakdown_stats,
    build_exit_reason_payload,
)
from .exit_charts.scatter import build_exit_mfe_mae_payload
from .exit_charts.volatility import build_exit_vol_regime_payload

__all__ = [
    "build_exit_holding_time_payload",
    "build_exit_mfe_mae_payload",
    "build_exit_pnl_decay_payload",
    "build_exit_reason_breakdown_stats",
    "build_exit_reason_payload",
    "build_exit_vol_regime_payload",
]
