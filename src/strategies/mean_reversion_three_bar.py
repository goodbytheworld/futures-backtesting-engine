# GC 5m works good!

"""
3-Bar mean reversion setup (CME / single-asset backtest).

IMPORTANT — execution model:
    The original discretionary rule set uses limit entries (long: close minus a
    small ATR fraction; short: close plus the same). This repository's single-
    asset engine exercises those signals with MARKET orders only (next-bar open
    fills per engine contract). Treat results as an aggressive fill
    approximation until limit-order execution exists in the engine.

Rules (signal evaluated at bar close; orders fill at the following bar open):
    Long:
        • Three consecutive down closes: C[t] < C[t-1] < C[t-2].
        • Current bar's low is the lowest low of the last N bars (including t).
        • Regime: prior completed daily close > rolling daily SMA (default 50).
    Short:
        • Three consecutive up closes: C[t] > C[t-1] > C[t-2].
        • Current bar's high is the highest high of the last N bars.
        • Regime: prior completed daily close <= that SMA (strict bear / not-bull).
    Exit:
        • Flat at the session's last bar of the entry day (same calendar day as
          the bar where the entry fill occurs — engine executes that exit at the
          daily close when applicable).

All masks are pre-computed in __init__; on_bar() is O(1) lookup + state.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.backtest_engine.execution import Order
from src.strategies.base import BaseStrategy


@dataclass
class ThreeBarMeanReversionConfig:
    """
    Parameters for the 3-bar mean reversion strategy.

    regime_window:
        Length of the simple moving average on daily last closes for trend filter.
    extreme_lookback:
        Bars in the rolling window for the “lowest low / highest high” clause
        (spec uses 5).
    trade_direction:
        "both" | "long" | "short"
    """

    regime_window: int = 50
    extreme_lookback: int = 5
    trade_direction: str = "both"


class ThreeBarMeanReversionStrategy(BaseStrategy):
    """Pre-computed 3-bar mean reversion signals with session EOD flat exit."""

    def __init__(self, engine, config: Optional[ThreeBarMeanReversionConfig] = None) -> None:
        super().__init__(engine)
        cfg = config or ThreeBarMeanReversionConfig()

        for field in dataclasses.fields(cfg):
            wfo_key = f"tbar_{field.name}"
            if hasattr(engine.settings, wfo_key):
                setattr(cfg, field.name, getattr(engine.settings, wfo_key))

        self.config = cfg

        close = engine.data["close"].astype(float)
        low = engine.data["low"].astype(float)
        high = engine.data["high"].astype(float)

        c0, c1, c2 = close, close.shift(1), close.shift(2)
        falling_3 = (c0 < c1) & (c1 < c2)
        rising_3 = (c0 > c1) & (c1 > c2)

        lb = cfg.extreme_lookback
        rolling_low_min = low.rolling(lb, min_periods=lb).min()
        rolling_high_max = high.rolling(lb, min_periods=lb).max()
        long_extreme = low <= rolling_low_min
        short_extreme = high >= rolling_high_max

        daily_last = close.resample("1D").last().dropna()
        sma_d = daily_last.rolling(cfg.regime_window, min_periods=cfg.regime_window).mean()
        # float64 avoids object-dtype ffill warnings when expanding daily mask to intraday
        daily_bull_f = (daily_last > sma_d).astype(np.float64)
        regime_prior = daily_bull_f.shift(1)
        regime_ff = regime_prior.reindex(close.index).ffill()
        valid_regime = regime_ff.notna()
        bull = (regime_ff == 1.0) & valid_regime
        bear = (regime_ff == 0.0) & valid_regime
        long_sig = falling_3 & long_extreme & bull
        short_sig = rising_3 & short_extreme & bear

        self._long_sig = long_sig
        self._short_sig = short_sig

        n = len(close)
        ts_list = close.index.to_list()
        self._ts_to_pos = {ts: i for i, ts in enumerate(ts_list)}
        dates_np = np.array([ts.date() if hasattr(ts, "date") else ts for ts in ts_list], dtype=object)
        is_eod = np.zeros(n, dtype=bool)
        if n > 0:
            is_eod[-1] = True
        if n > 1:
            is_eod[:-1] = dates_np[1:] != dates_np[:-1]
        self._is_eod = pd.Series(is_eod, index=close.index)
        self._bar_dates = dates_np

        self._invested = False
        self._position_side: Optional[str] = None
        self._exit_session_date: Optional[date] = None

        n_long = int(long_sig.sum())
        n_short = int(short_sig.sum())
        print(
            f"[3Bar MR] Ready | regime_SMA={cfg.regime_window}d | lookback={lb} | "
            f"long={n_long:,} short={n_short:,} bars"
        )

    def on_bar(self, bar: pd.Series) -> List[Order]:
        ts = bar.name

        try:
            pos = self._ts_to_pos[ts]
        except KeyError:
            return []

        orders: List[Order] = []

        if self._invested:
            cur_d = self._bar_dates[pos]
            eod = bool(self._is_eod.loc[ts])
            if cur_d == self._exit_session_date and eod:
                if self._position_side == "LONG":
                    orders.append(
                        self.market_order("SELL", self.settings.fixed_qty, reason="EOD_FLAT")
                    )
                else:
                    orders.append(
                        self.market_order("BUY", self.settings.fixed_qty, reason="EOD_FLAT")
                    )
                self._reset_position_state()
            return orders

        long_ok = bool(self._long_sig.loc[ts])
        short_ok = bool(self._short_sig.loc[ts])

        direction = self.config.trade_direction.lower()
        if direction == "long":
            short_ok = False
        elif direction == "short":
            long_ok = False

        if not long_ok and not short_ok:
            return orders

        if pos + 1 >= len(self._bar_dates):
            return orders

        self._exit_session_date = self._bar_dates[pos + 1]

        if long_ok:
            self._invested = True
            self._position_side = "LONG"
            orders.append(
                self.market_order("BUY", self.settings.fixed_qty, reason="MR3_LONG")
            )
        elif short_ok:
            self._invested = True
            self._position_side = "SHORT"
            orders.append(
                self.market_order("SELL", self.settings.fixed_qty, reason="MR3_SHORT")
            )

        return orders

    def _reset_position_state(self) -> None:
        self._invested = False
        self._position_side = None
        self._exit_session_date = None

    @classmethod
    def get_search_space(cls) -> Dict[str, Any]:
        return {
            "tbar_regime_window": (30, 90, 10),
            "tbar_extreme_lookback": (3, 7, 1),
        }
