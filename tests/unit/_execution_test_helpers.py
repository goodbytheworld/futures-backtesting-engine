from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class StubSettings:
    commission_rate: float = 2.5
    spread_ticks: int = 0
    spread_mode: str = "static"
    spread_volatility_step_pct: float = 0.10
    spread_step_multiplier: float = 1.5
    spread_vol_lookback: int = 20
    spread_vol_baseline_lookback: int = 100
    spread_tick_multipliers_by_order_type: dict = None
    commission_rate_by_order_type: dict = None
    intrabar_conflict_resolution: str = "pessimistic"
    intrabar_resolution_timeframe: str | None = None

    def get_instrument_spec(self, symbol: str) -> dict:
        return {"tick_size": 0.25, "multiplier": 50.0}


def _bar(timestamp: str, open_price: float) -> pd.Series:
    return pd.Series({"open": open_price, "close": open_price}, name=pd.Timestamp(timestamp))


def _ohlc_bar(
    timestamp: str,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
) -> pd.Series:
    return pd.Series(
        {
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
        },
        name=pd.Timestamp(timestamp),
    )
