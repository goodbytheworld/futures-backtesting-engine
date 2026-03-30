"""
Forward-horizon exit-analysis payload builders.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from src.backtest_engine.runtime.terminal_ui.constants import TITLE_EXIT_PNL_DECAY
from src.backtest_engine.services.artifact_service import ResultBundle

from .helpers import make_empty_payload, filter_trades_for_strategy


def _format_horizon(minutes: int) -> str:
    """Formats a minute horizon into the UI category label."""
    if minutes < 60:
        return f"{minutes}m"
    if minutes < 1440:
        return f"{minutes // 60}h"
    return f"{minutes // 1440}d"


def build_exit_pnl_decay_payload(
    bundle: ResultBundle,
    strategy_name: str = "__all__",
) -> dict[str, Any]:
    """
    Builds a category-line payload for forward-horizon PnL decay analysis.

    Methodology:
        Each horizon estimates average PnL if the trade had been closed at that
        fixed forward point instead of the actual exit. Horizons stop at the
        first bucket greater than or equal to observed max hold time so short
        strategies do not render irrelevant trailing gaps.

    Args:
        bundle: Active result bundle.
        strategy_name: Strategy label, ``__all__``, or empty string.

    Returns:
        Category-line payload for the terminal UI.
    """
    trades = filter_trades_for_strategy(bundle, strategy_name)
    if trades.empty:
        return make_empty_payload(
            TITLE_EXIT_PNL_DECAY,
            thresholds=[],
            verticalMarkers=[],
        )

    all_horizons = [5, 15, 30, 60, 120, 240, 480, 720, 1440]
    max_hold = float("inf")
    if "entry_time" in trades.columns and "exit_time" in trades.columns:
        durations_min = (
            pd.to_datetime(trades["exit_time"]) - pd.to_datetime(trades["entry_time"])
        ).dt.total_seconds() / 60.0
        valid = durations_min.dropna()
        if not valid.empty:
            max_hold = float(valid.max())
        if pd.isna(max_hold) or max_hold <= 0:
            max_hold = float("inf")

    present_horizons: list[int] = []
    for horizon in all_horizons:
        if f"pnl_decay_{horizon}m" not in trades.columns:
            continue
        present_horizons.append(horizon)
        if horizon >= max_hold:
            break

    if not present_horizons:
        return make_empty_payload(
            TITLE_EXIT_PNL_DECAY,
            empty_reason="No pnl_decay_* columns found. Run with exit enrichment enabled.",
            thresholds=[],
            verticalMarkers=[],
        )

    categories = ["Entry"] + [_format_horizon(horizon) for horizon in present_horizons]
    avg_values: list[Optional[float]] = [0.0]
    for horizon in present_horizons:
        avg = trades[f"pnl_decay_{horizon}m"].mean()
        avg_values.append(float(avg) if pd.notna(avg) else None)

    actual_avg = float(trades["pnl"].mean()) if "pnl" in trades.columns else 0.0
    thresholds = [
        {
            "value": actual_avg,
            "label": f"Actual Avg ${actual_avg:,.0f}",
            "legend": "Actual Avg",
            "color": "#22C55E" if actual_avg >= 0 else "#EF4444",
        }
    ]
    vertical_markers: list[dict[str, Any]] = []

    if "exit_reason" in trades.columns and "pnl" in trades.columns:
        time_stop_mask = trades["exit_reason"].astype(str).str.contains(
            "TIME_STOP",
            na=False,
        )
        time_stop_rows = trades[time_stop_mask]
        if (
            not time_stop_rows.empty
            and "entry_time" in time_stop_rows.columns
            and "exit_time" in time_stop_rows.columns
        ):
            hold_minutes = (
                pd.to_datetime(time_stop_rows["exit_time"])
                - pd.to_datetime(time_stop_rows["entry_time"])
            ).dt.total_seconds() / 60.0
            hold_minutes = hold_minutes.dropna()
            hold_minutes = hold_minutes[hold_minutes >= 0]
            if not hold_minutes.empty:
                if hold_minutes.nunique() == 1:
                    representative_minutes = float(hold_minutes.iloc[0])
                    marker_label = f"Time Stop Hold {representative_minutes:.0f}m"
                else:
                    representative_minutes = float(hold_minutes.mean())
                    marker_label = f"Time Stop Avg Hold {representative_minutes:.0f}m"
                closest_horizon = min(
                    present_horizons,
                    key=lambda horizon: abs(float(horizon) - representative_minutes),
                )
                vertical_markers.append(
                    {
                        "category": _format_horizon(closest_horizon),
                        "label": marker_label,
                        "legend": "Time Stop Hold",
                        "color": "#F59E0B",
                    }
                )

    return {
        "title": TITLE_EXIT_PNL_DECAY,
        "categories": categories,
        "series": [
            {
                "name": "Hypothetical Decay",
                "color": "#3B82F6",
                "values": avg_values,
            }
        ],
        "thresholds": thresholds,
        "verticalMarkers": vertical_markers,
        "emptyReason": "",
    }
