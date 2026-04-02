from __future__ import annotations

import pandas as pd

from src.backtest_engine.analytics.exit_analysis import enrich_trades_with_exit_analytics


def test_exit_analytics_excludes_entry_bar_path() -> None:
    """MFE/MAE should start after entry so the pre-position entry bar is excluded."""
    idx = pd.to_datetime(
        [
            "2024-01-01 09:30:00",
            "2024-01-01 10:00:00",
            "2024-01-01 10:30:00",
        ]
    )
    market = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.5],
            "high": [150.0, 101.0, 103.0],
            "low": [99.0, 99.5, 98.0],
            "close": [100.0, 100.5, 102.0],
        },
        index=idx,
    )
    trades = pd.DataFrame(
        {
            "slot_id": [0],
            "symbol": ["TEST"],
            "direction": ["LONG"],
            "entry_time": [idx[0]],
            "exit_time": [idx[2]],
            "entry_price": [100.0],
            "quantity": [1.0],
            "commission": [0.0],
            "slippage": [0.0],
        }
    )

    enriched = enrich_trades_with_exit_analytics(trades, {(0, "TEST"): market})

    assert float(enriched.loc[0, "mfe"]) == 3.0
    assert float(enriched.loc[0, "mae"]) == -2.0


def test_exit_analytics_populates_pnl_decay_columns() -> None:
    """PnL decay should be populated by forward close lookup at T+N."""
    idx = pd.to_datetime(
        [
            "2024-01-01 09:30:00",
            "2024-01-01 09:35:00",
            "2024-01-01 09:45:00",
        ]
    )
    market = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [100.0, 101.0, 102.0],
            "low": [100.0, 101.0, 102.0],
            "close": [100.0, 101.0, 102.0],
        },
        index=idx,
    )
    trades = pd.DataFrame(
        {
            "slot_id": [0],
            "symbol": ["TEST"],
            "direction": ["LONG"],
            "entry_time": [idx[0]],
            "exit_time": [idx[2]],
            "entry_price": [100.0],
            "quantity": [1.0],
            "commission": [0.0],
            "slippage": [0.0],
        }
    )

    enriched = enrich_trades_with_exit_analytics(trades, {(0, "TEST"): market})

    assert float(enriched.loc[0, "pnl_decay_5m"]) == 1.0
    assert float(enriched.loc[0, "pnl_decay_15m"]) == 2.0
