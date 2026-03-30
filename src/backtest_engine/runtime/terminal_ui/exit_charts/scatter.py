"""
Scatter-style exit-analysis payload builders.
"""

from __future__ import annotations

from typing import Any

from src.backtest_engine.runtime.terminal_ui.constants import TITLE_EXIT_MFE_MAE
from src.backtest_engine.services.artifact_service import ResultBundle

from .helpers import filter_trades_for_strategy


def build_exit_mfe_mae_payload(
    bundle: ResultBundle,
    strategy_name: str = "__all__",
) -> dict[str, Any]:
    """
    Builds a scatter payload for MFE vs MAE visualization.

    Methodology:
        Each trade is plotted at ``(MAE, MFE)``. Winners and losers are
        rendered as separate colored series, and a break-even diagonal helps
        analysts distinguish trades that recovered from adverse excursion.

    Args:
        bundle: Active result bundle.
        strategy_name: Strategy label, ``__all__``, or empty string.

    Returns:
        Scatter payload dictionary for the terminal UI.
    """
    trades = filter_trades_for_strategy(bundle, strategy_name)
    if trades.empty or "mfe" not in trades.columns or "mae" not in trades.columns:
        return {
            "title": TITLE_EXIT_MFE_MAE,
            "series": [],
            "emptyReason": "MFE/MAE columns unavailable for this bundle.",
        }

    subset = trades.dropna(subset=["mfe", "mae", "pnl"])
    if subset.empty:
        return {
            "title": TITLE_EXIT_MFE_MAE,
            "series": [],
            "emptyReason": "No complete MFE / MAE / PnL rows found.",
        }

    wins = subset[subset["pnl"] >= 0]
    losses = subset[subset["pnl"] < 0]
    series: list[dict[str, Any]] = []
    if not wins.empty:
        series.append(
            {
                "name": "Winners",
                "color": "#22C55E",
                "points": [
                    {"x": float(x), "y": float(y), "pnl": float(pnl)}
                    for x, y, pnl in zip(wins["mae"], wins["mfe"], wins["pnl"])
                ],
            }
        )
    if not losses.empty:
        series.append(
            {
                "name": "Losers",
                "color": "#EF4444",
                "points": [
                    {"x": float(x), "y": float(y), "pnl": float(pnl)}
                    for x, y, pnl in zip(losses["mae"], losses["mfe"], losses["pnl"])
                ],
            }
        )

    min_mae = float(subset["mae"].min())
    return {
        "title": TITLE_EXIT_MFE_MAE,
        "xAxisLabel": "MAE ($) [Adverse]",
        "yAxisLabel": "MFE ($) [Favorable]",
        "xAxisReversed": True,
        "series": series,
        "diagonal": {
            "x1": 0.0,
            "y1": 0.0,
            "x2": min_mae,
            "y2": float(abs(min_mae)),
        },
        "emptyReason": "",
    }
