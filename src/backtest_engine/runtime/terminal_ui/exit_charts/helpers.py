"""
Shared helpers for exit-analysis payload builders.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.backtest_engine.services.artifact_service import ResultBundle


def filter_trades_for_strategy(
    bundle: ResultBundle,
    strategy_name: str,
) -> pd.DataFrame:
    """
    Returns a strategy-filtered trade frame for exit-analysis builders.

    Methodology:
        Portfolio bundles may contain multiple strategy names in one trade log.
        Single-asset bundles ignore the filter because all rows already belong
        to the same strategy context.

    Args:
        bundle: Active result bundle.
        strategy_name: Requested strategy name, ``__all__``, or empty string.

    Returns:
        Defensive copy of the relevant trades.
    """
    trades = bundle.trades.copy() if bundle.trades is not None else pd.DataFrame()
    if trades.empty:
        return trades
    if (
        bundle.run_type == "portfolio"
        and strategy_name not in {"", "__all__"}
        and "strategy" in trades.columns
    ):
        trades = trades[trades["strategy"] == strategy_name].copy()
    return trades


def make_empty_payload(
    title: str,
    *,
    empty_reason: str = "",
    **extra: Any,
) -> dict[str, Any]:
    """
    Builds a consistent empty chart payload.

    Args:
        title: Chart title.
        empty_reason: Optional analyst-facing explanation.
        **extra: Additional payload keys.

    Returns:
        JSON-safe empty payload dictionary.
    """
    payload: dict[str, Any] = {
        "title": title,
        "categories": [],
        "series": [],
        "emptyReason": empty_reason,
    }
    payload.update(extra)
    return payload
