"""
Volatility-regime exit-analysis payload builders.
"""

from __future__ import annotations

import pandas as pd

from src.backtest_engine.runtime.terminal_ui.constants import TITLE_EXIT_VOL_REGIME
from src.backtest_engine.services.artifact_service import ResultBundle
from src.backtest_engine.config import BacktestSettings

from .helpers import make_empty_payload, filter_trades_for_strategy


def build_exit_vol_regime_payload(
    bundle: ResultBundle,
    strategy_name: str = "__all__",
) -> dict[str, object]:
    """
    Builds a bar payload for average PnL by entry volatility regime.

    Methodology:
        The builder consumes pre-enriched ``entry_volatility`` values and
        groups them into Compression, Normal, and Panic buckets using either
        per-trade configuration columns or shared settings defaults.

    Args:
        bundle: Active result bundle.
        strategy_name: Strategy label, ``__all__``, or empty string.

    Returns:
        Bar payload dictionary for the terminal UI.
    """
    trades = filter_trades_for_strategy(bundle, strategy_name)
    if trades.empty or "entry_volatility" not in trades.columns:
        return make_empty_payload(
            TITLE_EXIT_VOL_REGIME,
            empty_reason="entry_volatility column not found. Run with exit enrichment enabled.",
        )

    subset = trades.dropna(subset=["entry_volatility", "pnl"]).copy()
    if subset.empty:
        return make_empty_payload(
            TITLE_EXIT_VOL_REGIME,
            empty_reason="No complete entry_volatility / pnl rows found.",
        )

    settings = BacktestSettings()
    vol_min = (
        float(trades["vol_min_pct"].iloc[0])
        if "vol_min_pct" in trades.columns and pd.notna(trades["vol_min_pct"].iloc[0])
        else settings.vol_min_pct_default
    )
    vol_max = (
        float(trades["vol_max_pct"].iloc[0])
        if "vol_max_pct" in trades.columns and pd.notna(trades["vol_max_pct"].iloc[0])
        else settings.vol_max_pct_default
    )

    vol_min = max(0.00001, min(vol_min, 0.99998))
    vol_max = max(vol_min + 0.00001, min(vol_max, 0.99999))
    bucket_labels = ["Compression", "Normal", "Panic"]

    try:
        subset["vol_bucket"] = pd.cut(
            subset["entry_volatility"],
            bins=[0.0, vol_min, vol_max, 1.0],
            labels=bucket_labels,
            include_lowest=True,
        )
    except Exception as exc:
        return make_empty_payload(
            TITLE_EXIT_VOL_REGIME,
            empty_reason=(
                "Invalid volatility distribution "
                f"(bucket construction failed: {exc})."
            ),
        )

    grouped = (
        subset.groupby("vol_bucket", observed=False)
        .agg(avg_pnl=("pnl", "mean"))
        .fillna(0)
    )
    avg_values = [float(value) for value in grouped["avg_pnl"]]
    item_colors = ["#22C55E" if value >= 0 else "#EF4444" for value in avg_values]
    return {
        "title": TITLE_EXIT_VOL_REGIME,
        "categories": bucket_labels,
        "series": [
            {
                "name": "Avg PnL per Trade",
                "values": avg_values,
                "itemColors": item_colors,
                "yAxisIndex": 0,
            }
        ],
        "hideLegend": True,
        "emptyReason": "",
    }
