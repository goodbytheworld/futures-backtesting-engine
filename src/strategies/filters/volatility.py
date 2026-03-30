"""
Volatility-aware trade filters.

These filters operate on precomputed series and expose simple timestamp-based
queries so strategies can keep ``on_bar()`` logic lightweight.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .core import wilder_atr


class VolatilityRegimeFilter:
    """
    Blocks trading in extreme low- or high-volatility regimes.

    Methodology:
        Rolling volatility is ranked inside a longer historical window to
        obtain a percentile regime label. The label is shifted by one bar so a
        strategy only consumes completed information and never peeks forward.
    """

    def __init__(
        self,
        price: pd.Series,
        regime_window: int,
        history_window: int,
        min_pct: float = 0.20,
        max_pct: float = 0.80,
    ) -> None:
        """
        Initializes the volatility regime filter.

        Args:
            price: Close-price or reference-value series.
            regime_window: Rolling window for current volatility estimation.
            history_window: Rolling window for percentile ranking.
            min_pct: Lower percentile gate.
            max_pct: Upper percentile gate.
        """
        self.min_pct = min_pct
        self.max_pct = max_pct
        rolling_vol = price.rolling(
            window=regime_window,
            min_periods=regime_window // 2,
        ).std()
        vol_pct = rolling_vol.rolling(
            window=history_window,
            min_periods=history_window // 2,
        ).rank(pct=True)
        self._pct: pd.Series = vol_pct.shift(1)

    def is_allowed(self, timestamp: object) -> bool:
        """
        Returns whether the completed volatility regime permits trading.

        Args:
            timestamp: Bar index label to query.

        Returns:
            ``True`` when the percentile lies inside the configured bounds.
        """
        try:
            pct = self._pct.at[timestamp]
        except KeyError:
            return True
        if np.isnan(pct):
            return True
        return self.min_pct <= pct <= self.max_pct

    def as_series(self) -> pd.Series:
        """Returns the shifted volatility-percentile series."""
        return self._pct


class ShockFilter:
    """
    Blocks entries after abnormally violent bars and opening gaps.

    Methodology:
        Prior-bar ATR acts as a stable volatility baseline. Gaps, intrabar
        ranges, and close-to-close moves are normalized by that baseline and
        blocked when they exceed the configured multiples.
    """

    def __init__(
        self,
        open_: pd.Series,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        atr_window: int = 14,
        max_gap_atr: float = 1.0,
        max_range_atr: float = 2.5,
        max_close_change_atr: float = 1.75,
    ) -> None:
        """
        Initializes the shock filter.

        Args:
            open_: Open-price series.
            high: High-price series.
            low: Low-price series.
            close: Close-price series.
            atr_window: ATR lookback used as the shock baseline.
            max_gap_atr: Maximum gap size in ATR units.
            max_range_atr: Maximum bar range in ATR units.
            max_close_change_atr: Maximum close-to-close move in ATR units.
        """
        atr_ref = wilder_atr(high, low, close, atr_window).shift(1)
        prev_close = close.shift(1)

        gap_atr = (open_ - prev_close).abs() / atr_ref
        range_atr = (high - low).abs() / atr_ref
        close_change_atr = (close - prev_close).abs() / atr_ref

        allowed = (
            (gap_atr <= max_gap_atr)
            & (range_atr <= max_range_atr)
            & (close_change_atr <= max_close_change_atr)
        ).where(atr_ref.notna(), True)

        self._allowed: pd.Series = allowed.fillna(True)
        self._gap_atr: pd.Series = gap_atr
        self._range_atr: pd.Series = range_atr
        self._close_change_atr: pd.Series = close_change_atr

    def is_allowed(self, timestamp: object) -> bool:
        """
        Returns whether the queried bar passes the shock gate.

        Args:
            timestamp: Bar index label to query.

        Returns:
            ``True`` when the bar is not classified as a shock bar.
        """
        try:
            return bool(self._allowed.at[timestamp])
        except KeyError:
            return True

    def as_series(self) -> pd.Series:
        """Returns the boolean allow/block mask."""
        return self._allowed

    def diagnostics(self) -> pd.DataFrame:
        """
        Returns ATR-normalized shock diagnostics for debugging and plotting.

        Returns:
            DataFrame with gap, range, close-change, and final allow mask.
        """
        return pd.DataFrame(
            {
                "gap_atr": self._gap_atr,
                "range_atr": self._range_atr,
                "close_change_atr": self._close_change_atr,
                "allowed": self._allowed,
            }
        )


class AtrStretchFilter:
    """
    Blocks entries when price is already too far from a local baseline.

    Methodology:
        An EMA baseline approximates short-term equilibrium. Signed distance
        from that baseline is normalized by prior ATR, allowing long and short
        stretch thresholds to be compared on the same volatility-adjusted
        scale.
    """

    def __init__(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        baseline_window: int = 20,
        atr_window: int = 14,
        max_long_stretch_atr: float = 1.75,
        max_short_stretch_atr: float = 1.75,
    ) -> None:
        """
        Initializes the ATR stretch filter.

        Args:
            high: High-price series.
            low: Low-price series.
            close: Close-price series.
            baseline_window: EMA span for the local baseline.
            atr_window: ATR lookback used for normalization.
            max_long_stretch_atr: Max positive stretch allowed for longs.
            max_short_stretch_atr: Max negative stretch allowed for shorts.
        """
        baseline = close.ewm(span=baseline_window, adjust=False).mean()
        atr_ref = wilder_atr(high, low, close, atr_window).shift(1)
        signed_stretch = (close - baseline) / atr_ref

        self.max_long_stretch_atr = max_long_stretch_atr
        self.max_short_stretch_atr = max_short_stretch_atr
        self._signed_stretch: pd.Series = signed_stretch
        self._long_allowed: pd.Series = (
            (signed_stretch <= max_long_stretch_atr)
            .where(atr_ref.notna(), True)
            .fillna(True)
        )
        self._short_allowed: pd.Series = (
            (signed_stretch >= -max_short_stretch_atr)
            .where(atr_ref.notna(), True)
            .fillna(True)
        )

    def is_long_allowed(self, timestamp: object) -> bool:
        """
        Returns whether long entries remain within the stretch threshold.

        Args:
            timestamp: Bar index label to query.

        Returns:
            ``True`` when long stretch is acceptable.
        """
        try:
            return bool(self._long_allowed.at[timestamp])
        except KeyError:
            return True

    def is_short_allowed(self, timestamp: object) -> bool:
        """
        Returns whether short entries remain within the stretch threshold.

        Args:
            timestamp: Bar index label to query.

        Returns:
            ``True`` when short stretch is acceptable.
        """
        try:
            return bool(self._short_allowed.at[timestamp])
        except KeyError:
            return True

    def is_allowed(self, timestamp: object) -> bool:
        """
        Returns whether both sides remain inside their stretch thresholds.

        Args:
            timestamp: Bar index label to query.

        Returns:
            ``True`` when the absolute stretch is not extreme.
        """
        return self.is_long_allowed(timestamp) and self.is_short_allowed(timestamp)

    def get(self, timestamp: object, default: float = np.nan) -> float:
        """
        Returns the signed ATR-normalized stretch value.

        Args:
            timestamp: Bar index label to query.
            default: Fallback value when the timestamp is unavailable.

        Returns:
            Signed stretch in ATR units.
        """
        try:
            value = self._signed_stretch.at[timestamp]
        except KeyError:
            return default
        return float(value) if not np.isnan(value) else default

    def as_series(self) -> pd.Series:
        """Returns the signed stretch series in ATR units."""
        return self._signed_stretch
