"""
Keltner Channel tightening breakout strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.backtest_engine.execution import Order
from src.strategies.base import BaseStrategy
from src.strategies.filters import (
    ShockFilter,
    apply_wfo_dataclass_overrides,
    gate_trade_direction,
    keltner_channels,
    rolling_range_levels,
    rolling_volume_ratio,
    wilder_atr,
)


@dataclass
class KeltnerTighteningBreakoutConfig:
    """
    Parameters for the Keltner tightening breakout strategy.

    Methodology:
        The strategy looks for tight Keltner Channels, then enters through the
        completed range once both price and volatility start expanding.
    """

    kc_ema_window: int = 20
    kc_atr_window: int = 20
    kc_atr_mult: float = 1.5
    tightening_lookback: int = 100
    tightening_quantile: float = 0.25
    tightening_memory: int = 5
    width_expansion_factor: float = 1.03
    breakout_lookback: int = 20
    volume_window: int = 20
    breakout_volume_ratio: float = 1.25
    risk_atr_window: int = 14
    stop_atr_buffer: float = 0.60
    target_rr: float = 1.60
    entry_buffer_ticks: int = 1
    trade_direction: str = "long"  # "both" | "long" | "short"
    use_shock_filter: bool = True
    shock_atr_window: int = 14
    shock_max_gap_atr: float = 1.50
    shock_max_range_atr: float = 3.75
    shock_max_close_change_atr: float = 2.25


class KeltnerTighteningBreakoutStrategy(BaseStrategy):
    """
    Trades breakouts that emerge from Keltner Channel tightening.
    """

    strategy_tag = "KCTG"

    def __init__(
        self,
        engine,
        config: Optional[KeltnerTighteningBreakoutConfig] = None,
    ) -> None:
        super().__init__(engine)
        cfg = config or KeltnerTighteningBreakoutConfig()
        apply_wfo_dataclass_overrides(engine, cfg, "kctg")
        self.config = cfg

        close = engine.data["close"].astype(float)
        open_ = engine.data["open"].astype(float)
        high = engine.data["high"].astype(float)
        low = engine.data["low"].astype(float)
        volume = engine.data["volume"].astype(float)
        tick_size = float(
            self.settings.get_instrument_spec(self.settings.default_symbol)["tick_size"]
        )
        entry_buffer = tick_size * max(1, int(cfg.entry_buffer_ticks))

        channels = keltner_channels(
            high=high,
            low=low,
            close=close,
            ema_window=cfg.kc_ema_window,
            atr_window=cfg.kc_atr_window,
            atr_mult=cfg.kc_atr_mult,
        )
        range_levels = rolling_range_levels(high=high, low=low, lookback=cfg.breakout_lookback)
        atr = wilder_atr(high=high, low=low, close=close, span=cfg.risk_atr_window)
        volume_ratio = rolling_volume_ratio(volume=volume, window=cfg.volume_window)

        width_threshold = channels.normalized_width.rolling(
            cfg.tightening_lookback,
            min_periods=min(cfg.tightening_lookback, max(5, cfg.tightening_lookback // 2)),
        ).quantile(cfg.tightening_quantile)
        tightening = (channels.normalized_width <= width_threshold).fillna(False)
        recent_tightening = (
            tightening.shift(1)
            .rolling(cfg.tightening_memory, min_periods=1)
            .max()
            .fillna(0.0)
            > 0.0
        )
        width_expanding = (
            channels.normalized_width
            > channels.normalized_width.shift(1) * float(cfg.width_expansion_factor)
        )

        long_sig = (
            recent_tightening
            & width_expanding.fillna(False)
            & range_levels.resistance.notna()
            & (close > range_levels.resistance)
            & (high >= channels.upper)
            & (volume_ratio >= cfg.breakout_volume_ratio)
        )
        short_sig = (
            recent_tightening
            & width_expanding.fillna(False)
            & range_levels.support.notna()
            & (close < range_levels.support)
            & (low <= channels.lower)
            & (volume_ratio >= cfg.breakout_volume_ratio)
        )

        projected_move = pd.concat([range_levels.height, atr], axis=1).max(axis=1)

        self._long_sig = long_sig.fillna(False)
        self._short_sig = short_sig.fillna(False)
        self._long_entry_stop = range_levels.resistance + entry_buffer
        self._short_entry_stop = range_levels.support - entry_buffer
        self._long_stop_loss = range_levels.support - atr * float(cfg.stop_atr_buffer)
        self._short_stop_loss = range_levels.resistance + atr * float(cfg.stop_atr_buffer)
        self._long_target = self._long_entry_stop + projected_move * float(cfg.target_rr)
        self._short_target = self._short_entry_stop - projected_move * float(cfg.target_rr)

        self._shock_filter: Optional[ShockFilter] = None
        if cfg.use_shock_filter:
            self._shock_filter = ShockFilter(
                open_=open_,
                high=high,
                low=low,
                close=close,
                atr_window=cfg.shock_atr_window,
                max_gap_atr=cfg.shock_max_gap_atr,
                max_range_atr=cfg.shock_max_range_atr,
                max_close_change_atr=cfg.shock_max_close_change_atr,
            )

        self._pending_side: Optional[str] = None
        self._pending_stop_price: float = np.nan
        self._pending_target_price: float = np.nan
        self._active_side: Optional[str] = None
        self._active_stop_price: float = np.nan
        self._active_target_price: float = np.nan
        self._bracket_sent: bool = False
        self._invested = False
        self._position_side: Optional[str] = None

        print(
            f"[Keltner Tightening] Ready | ema={cfg.kc_ema_window} | "
            f"range={cfg.breakout_lookback} | long={int(self._long_sig.sum()):,} "
            f"short={int(self._short_sig.sum()):,}"
        )

    def on_bar(self, bar: pd.Series) -> List[Order]:
        ts = bar.name
        current_qty = float(self.get_position())

        if current_qty > 0.0:
            self._invested = True
            self._position_side = "LONG"
            return self._emit_protective_bracket(ts=ts, side="LONG")
        if current_qty < 0.0:
            self._invested = True
            self._position_side = "SHORT"
            return self._emit_protective_bracket(ts=ts, side="SHORT")

        if self._invested or self._active_side is not None:
            self._reset_trade_state()
        else:
            self._clear_pending_entry()

        long_ok = self._signal_at(self._long_sig, ts)
        short_ok = self._signal_at(self._short_sig, ts)

        if self._shock_filter is not None and not self._shock_filter.is_allowed(ts):
            long_ok = False
            short_ok = False

        long_ok, short_ok = gate_trade_direction(
            self.config.trade_direction,
            long_ok,
            short_ok,
        )
        if long_ok and short_ok:
            return []

        if long_ok:
            order = self._build_entry_order(ts=ts, side="LONG")
            return [order] if order is not None else []
        if short_ok:
            order = self._build_entry_order(ts=ts, side="SHORT")
            return [order] if order is not None else []
        return []

    def _emit_protective_bracket(self, ts: object, side: str) -> List[Order]:
        if self._active_side != side:
            self._active_side = side
            self._bracket_sent = False
            if self._pending_side == side:
                self._active_stop_price = self._pending_stop_price
                self._active_target_price = self._pending_target_price
            else:
                stop_series = self._long_stop_loss if side == "LONG" else self._short_stop_loss
                target_series = self._long_target if side == "LONG" else self._short_target
                self._active_stop_price = self._series_value(stop_series, ts)
                self._active_target_price = self._series_value(target_series, ts)
            self._clear_pending_entry()

        if self._bracket_sent:
            return []
        if not (
            np.isfinite(self._active_stop_price) and np.isfinite(self._active_target_price)
        ):
            return []

        self._bracket_sent = True
        qty = self.settings.fixed_qty
        if side == "LONG":
            return [
                self.stop_order(
                    "SELL",
                    qty,
                    stop_price=float(self._active_stop_price),
                    reason=f"{self.strategy_tag}_LONG_SL",
                    reduce_only=True,
                ),
                self.limit_order(
                    "SELL",
                    qty,
                    limit_price=float(self._active_target_price),
                    reason=f"{self.strategy_tag}_LONG_TP",
                    reduce_only=True,
                ),
            ]
        return [
            self.stop_order(
                "BUY",
                qty,
                stop_price=float(self._active_stop_price),
                reason=f"{self.strategy_tag}_SHORT_SL",
                reduce_only=True,
            ),
            self.limit_order(
                "BUY",
                qty,
                limit_price=float(self._active_target_price),
                reason=f"{self.strategy_tag}_SHORT_TP",
                reduce_only=True,
            ),
        ]

    def _build_entry_order(self, ts: object, side: str) -> Optional[Order]:
        if side == "LONG":
            entry_stop = self._series_value(self._long_entry_stop, ts)
            stop_loss = self._series_value(self._long_stop_loss, ts)
            target = self._series_value(self._long_target, ts)
            if not self._valid_long_setup(entry_stop, stop_loss, target):
                return None
            self._pending_side = "LONG"
            self._pending_stop_price = stop_loss
            self._pending_target_price = target
            return self.stop_order(
                "BUY",
                self.settings.fixed_qty,
                stop_price=float(entry_stop),
                reason=f"{self.strategy_tag}_LONG_ENTRY",
                time_in_force="IOC",
            )

        entry_stop = self._series_value(self._short_entry_stop, ts)
        stop_loss = self._series_value(self._short_stop_loss, ts)
        target = self._series_value(self._short_target, ts)
        if not self._valid_short_setup(entry_stop, stop_loss, target):
            return None
        self._pending_side = "SHORT"
        self._pending_stop_price = stop_loss
        self._pending_target_price = target
        return self.stop_order(
            "SELL",
            self.settings.fixed_qty,
            stop_price=float(entry_stop),
            reason=f"{self.strategy_tag}_SHORT_ENTRY",
            time_in_force="IOC",
        )

    @staticmethod
    def _signal_at(series: pd.Series, ts: object) -> bool:
        try:
            return bool(series.at[ts])
        except KeyError:
            return False

    @staticmethod
    def _series_value(series: pd.Series, ts: object) -> float:
        try:
            value = series.at[ts]
        except KeyError:
            return np.nan
        return float(value) if pd.notna(value) else np.nan

    def _clear_pending_entry(self) -> None:
        self._pending_side = None
        self._pending_stop_price = np.nan
        self._pending_target_price = np.nan

    def _reset_trade_state(self) -> None:
        self._clear_pending_entry()
        self._active_side = None
        self._active_stop_price = np.nan
        self._active_target_price = np.nan
        self._bracket_sent = False
        self._invested = False
        self._position_side = None

    @staticmethod
    def _valid_long_setup(entry_stop: float, stop_loss: float, target: float) -> bool:
        return (
            np.isfinite(entry_stop)
            and np.isfinite(stop_loss)
            and np.isfinite(target)
            and stop_loss < entry_stop < target
        )

    @staticmethod
    def _valid_short_setup(entry_stop: float, stop_loss: float, target: float) -> bool:
        return (
            np.isfinite(entry_stop)
            and np.isfinite(stop_loss)
            and np.isfinite(target)
            and target < entry_stop < stop_loss
        )

    @classmethod
    def get_search_space(cls) -> Dict[str, Any]:
        return {
            "kctg_kc_ema_window": (12, 30, 2),
            "kctg_kc_atr_window": (10, 30, 2),
            "kctg_breakout_lookback": (10, 40, 5),
            "kctg_breakout_volume_ratio": (1.10, 1.90, 0.10),
            "kctg_target_rr": (1.25, 2.25, 0.25),
        }
