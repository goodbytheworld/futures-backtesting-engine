"""
Holding-time exit-analysis payload builders.
"""

from __future__ import annotations

import pandas as pd

from src.backtest_engine.runtime.terminal_ui.constants import TITLE_EXIT_HOLDING_TIME
from src.backtest_engine.services.artifact_service import ResultBundle

from .helpers import make_empty_payload, filter_trades_for_strategy


def build_exit_holding_time_payload(
    bundle: ResultBundle,
    strategy_name: str = "__all__",
) -> dict[str, object]:
    """
    Builds a bar payload for average PnL by holding-time bucket.

    Methodology:
        Holding time is derived from ``exit_time - entry_time`` in minutes.
        Bucket size adapts to the observed maximum hold while keeping the chart
        fixed at five analyst-friendly categories.

    Args:
        bundle: Active result bundle.
        strategy_name: Strategy label, ``__all__``, or empty string.

    Returns:
        Bar payload dictionary for the terminal UI.
    """
    trades = filter_trades_for_strategy(bundle, strategy_name)
    if (
        trades.empty
        or "entry_time" not in trades.columns
        or "exit_time" not in trades.columns
    ):
        return make_empty_payload(TITLE_EXIT_HOLDING_TIME)

    durations_min = (
        pd.to_datetime(trades["exit_time"]) - pd.to_datetime(trades["entry_time"])
    ).dt.total_seconds() / 60.0
    valid_durations = durations_min.dropna()
    max_hold = float(valid_durations.max()) if not valid_durations.empty else 60.0
    if pd.isna(max_hold) or max_hold <= 0:
        max_hold = 60.0

    if max_hold <= 60:
        step, unit = 15, "m"
    elif max_hold <= 240:
        step, unit = 60, "m"
    elif max_hold <= 1440:
        step, unit = 360, "h"
    else:
        step, unit = 1440, "d"

    def format_bucket(minutes: float) -> str:
        if unit == "m":
            return f"{int(minutes)}m"
        if unit == "h":
            return f"{int(minutes / 60)}h"
        return f"{int(minutes / 1440)}d"

    b1, b2, b3, b4 = step, step * 2, step * 3, step * 4
    labels = [
        f"<{format_bucket(b1)}",
        f"{format_bucket(b1)}-{format_bucket(b2)}",
        f"{format_bucket(b2)}-{format_bucket(b3)}",
        f"{format_bucket(b3)}-{format_bucket(b4)}",
        f">{format_bucket(b4)}",
    ]

    trades_copy = trades.copy()
    trades_copy["hold_bucket"] = pd.cut(
        durations_min,
        bins=[0.0, float(b1), float(b2), float(b3), float(b4), float("inf")],
        labels=labels,
        right=False,
    )
    grouped = (
        trades_copy.groupby("hold_bucket", observed=False)
        .agg(avg_pnl=("pnl", "mean"), count=("pnl", "count"))
        .fillna(0)
    )
    avg_values = [float(value) for value in grouped["avg_pnl"]]
    item_colors = ["#22C55E" if value >= 0 else "#EF4444" for value in avg_values]
    return {
        "title": TITLE_EXIT_HOLDING_TIME,
        "categories": labels,
        "series": [
            {
                "name": "Avg PnL per Trade",
                "values": avg_values,
                "itemColors": item_colors,
                "yAxisIndex": 0,
            }
        ],
        "hideLegend": True,
    }
