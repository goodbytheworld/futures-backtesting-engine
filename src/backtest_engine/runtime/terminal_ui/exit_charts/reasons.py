"""
Exit-reason payload builders and summary stats.
"""

from __future__ import annotations

from typing import Any

from src.backtest_engine.runtime.terminal_ui.constants import TITLE_EXIT_REASON
from src.backtest_engine.services.artifact_service import ResultBundle

from .helpers import make_empty_payload, filter_trades_for_strategy


def build_exit_reason_payload(
    bundle: ResultBundle,
    strategy_name: str = "__all__",
) -> dict[str, object]:
    """
    Builds a bar payload for total PnL by exit reason.

    Args:
        bundle: Active result bundle.
        strategy_name: Strategy label, ``__all__``, or empty string.

    Returns:
        Bar payload dictionary for the terminal UI.
    """
    trades = filter_trades_for_strategy(bundle, strategy_name)
    if trades.empty or "exit_reason" not in trades.columns:
        return make_empty_payload(
            TITLE_EXIT_REASON,
            empty_reason="exit_reason column not available.",
        )

    grouped = (
        trades.groupby("exit_reason")
        .agg(total_pnl=("pnl", "sum"))
        .sort_values("total_pnl", ascending=False)
    )
    if grouped.empty:
        return make_empty_payload(
            TITLE_EXIT_REASON,
            empty_reason="No exit reason data found.",
        )

    categories = [str(reason) for reason in grouped.index.tolist()]
    total_values = [float(value) for value in grouped["total_pnl"]]
    item_colors = ["#22C55E" if value >= 0 else "#EF4444" for value in total_values]
    return {
        "title": TITLE_EXIT_REASON,
        "categories": categories,
        "series": [
            {
                "name": "Total PnL",
                "values": total_values,
                "itemColors": item_colors,
                "yAxisIndex": 0,
            }
        ],
        "hideLegend": True,
        "emptyReason": "",
    }


def build_exit_reason_breakdown_stats(
    bundle: ResultBundle,
    strategy_name: str = "__all__",
) -> list[dict[str, str]]:
    """
    Builds table rows for the exit-reason breakdown panel.

    Args:
        bundle: Active result bundle.
        strategy_name: Strategy label, ``__all__``, or empty string.

    Returns:
        List of formatted row dictionaries for Jinja templates.
    """
    trades = filter_trades_for_strategy(bundle, strategy_name)
    if (
        trades.empty
        or "exit_reason" not in trades.columns
        or "pnl" not in trades.columns
    ):
        return []

    grouped = trades.groupby("exit_reason").agg(
        count=("pnl", "count"),
        total_pnl=("pnl", "sum"),
        avg_pnl=("pnl", "mean"),
        wins=("pnl", lambda pnl: int((pnl >= 0).sum())),
    )
    grouped["win_rate"] = grouped["wins"] / grouped["count"]
    grouped = grouped.sort_values("total_pnl", ascending=False).reset_index()

    rows: list[dict[str, str]] = []
    for _, row in grouped.iterrows():
        rows.append(
            {
                "Exit Reason": str(row["exit_reason"]),
                "Count": str(int(row["count"])),
                "Win Rate": f"{float(row['win_rate']) * 100.0:.1f}%",
                "Avg PnL": f"${float(row['avg_pnl']):,.0f}",
                "Total PnL": f"${float(row['total_pnl']):,.0f}",
            }
        )
    return rows
