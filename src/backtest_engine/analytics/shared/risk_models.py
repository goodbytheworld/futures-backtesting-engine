"""
Data contracts for the dashboard Risk Analysis tab.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import pandas as pd


@dataclass(frozen=True)
class StressMultipliers:
    """User-controlled multipliers applied by the stress-test scenarios."""

    volatility: float
    slippage: float
    commission: float


@dataclass(frozen=True)
class RiskDashboardConfig:
    """
    Immutable configuration for the Risk Analysis tab.

    Methodology:
        The Streamlit layer reads these values from BacktestSettings once and
        passes a stable config object to the risk renderer and pure transforms.
    """

    var_confidence_primary: float
    var_confidence_tail: float
    rolling_var_window_days: int
    rolling_vol_windows: Tuple[int, ...]
    stress_slider_min: float
    stress_slider_max: float
    stress_slider_step: float
    stress_defaults: StressMultipliers


@dataclass
class StressScenarioResult:
    """Computed stress-test outcome for a single scenario."""

    name: str
    label: str
    equity: pd.Series
    daily_pnl: pd.Series
    metrics: Dict[str, float]
    pnl_delta: float


@dataclass
class RiskProfile:
    """
    Fully prepared risk payload for one analyzable stream.

    The same structure works for:
        1. Single-asset mode.
        2. Portfolio aggregate mode.
        3. Portfolio strategy drilldown mode.
    """

    label: str
    equity: pd.Series
    daily_pnl: pd.Series
    daily_returns: pd.Series
    drawdown: pd.Series
    drawdown_episodes: pd.DataFrame
    rolling_var: pd.DataFrame
    rolling_vol: pd.DataFrame
    summary: Dict[str, float]
    stress_results: List[StressScenarioResult]
