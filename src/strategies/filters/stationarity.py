"""
Stationarity and mean-reversion filters.
"""

from __future__ import annotations

import warnings
from typing import Optional

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller


class ADFFilter:
    """
    Blocks trading when a rolling ADF test suggests non-stationarity.

    Methodology:
        The input series is resampled to a slower timeframe, then a rolling ADF
        test is applied. The resulting p-values are forward-filled back to the
        original resolution and shifted one bar to preserve the no-lookahead
        contract.
    """

    def __init__(
        self,
        series: pd.Series,
        adf_window: int = 72,
        timeframe: str = "1h",
        max_pvalue: float = 0.05,
    ) -> None:
        """
        Initializes the ADF filter.

        Args:
            series: Price or spread series.
            adf_window: Number of resampled bars per test window.
            timeframe: Resample frequency passed to Pandas.
            max_pvalue: Maximum p-value still considered stationary.
        """
        self.max_pvalue = max_pvalue
        resampled = (
            series.resample(timeframe, label="right", closed="right")
            .last()
            .dropna()
        )
        pvalues = pd.Series(index=resampled.index, dtype=float, name="adf_pvalue")

        failures = 0
        for index in range(adf_window, len(resampled)):
            window_slice = resampled.iloc[index - adf_window : index]
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    result = adfuller(window_slice.values, maxlag=1, autolag=None)
                    pvalues.iloc[index] = result[1]
            except Exception:
                failures += 1
                pvalues.iloc[index] = np.nan

        if failures > 0:
            print(f"[ADFFilter] ADF fit failed on {failures} windows (NaN assigned).")

        self._pvalue: pd.Series = (
            pvalues.reindex(series.index, method="ffill")
            .shift(1)
            .reindex(series.index, method="ffill")
        )

    def is_allowed(self, timestamp: object) -> bool:
        """
        Returns whether the series still looks stationary at the queried bar.

        Args:
            timestamp: Bar index label to query.

        Returns:
            ``True`` when the p-value remains below ``max_pvalue``.
        """
        try:
            pvalue = self._pvalue.at[timestamp]
        except KeyError:
            return False
        if np.isnan(pvalue):
            return False
        return pvalue < self.max_pvalue

    def as_series(self) -> pd.Series:
        """Returns the shifted ADF p-value series."""
        return self._pvalue


class HalfLifeFilter:
    """
    Estimates rolling half-life of mean reversion for a series.

    Methodology:
        A rolling regression of ``dy`` on ``y[t-1]`` provides the local
        Ornstein-Uhlenbeck speed estimate. Valid negative slopes are converted
        into half-life and shifted by one bar so downstream strategy logic only
        consumes completed estimates.
    """

    def __init__(
        self,
        series: pd.Series,
        window: int = 100,
        max_half_life: float = 50.0,
        lambda_min: Optional[float] = 1e-4,
        max_cap: Optional[float] = 500.0,
    ) -> None:
        """
        Initializes the half-life filter.

        Args:
            series: Price or spread series.
            window: Rolling regression window.
            max_half_life: Maximum half-life still considered tradable.
            lambda_min: Minimum mean-reversion speed magnitude.
            max_cap: Hard cap for extreme half-life values.
        """
        self.max_half_life = max_half_life
        self.lambda_min = lambda_min
        self.max_cap = max_cap

        y_lag = series.shift(1)
        dy = series - y_lag

        var_x = y_lag.rolling(window=window, min_periods=window // 2).var()
        cov_xy = y_lag.rolling(window=window, min_periods=window // 2).cov(dy)
        slope = (cov_xy / var_x).replace([np.inf, -np.inf], np.nan)

        half_life = pd.Series(np.nan, index=series.index)
        if self.lambda_min is not None:
            valid_idx = slope < -abs(self.lambda_min)
        else:
            valid_idx = slope < -1e-8

        raw_half_life = -np.log(2) / slope[valid_idx]
        half_life[valid_idx] = (
            np.minimum(raw_half_life, self.max_cap)
            if self.max_cap is not None
            else raw_half_life
        )
        self._half_life: pd.Series = half_life.shift(1)

    def is_allowed(self, timestamp: object) -> bool:
        """
        Returns whether the estimated half-life remains short enough.

        Args:
            timestamp: Bar index label to query.

        Returns:
            ``True`` when the half-life is defined and within bounds.
        """
        try:
            half_life = self._half_life.at[timestamp]
        except KeyError:
            return False
        if np.isnan(half_life):
            return False
        return 0 < half_life <= self.max_half_life

    def get(self, timestamp: object, default: float = np.nan) -> float:
        """
        Returns the raw half-life estimate for a bar.

        Args:
            timestamp: Bar index label to query.
            default: Fallback value when no estimate is available.

        Returns:
            Half-life estimate or ``default``.
        """
        try:
            half_life = self._half_life.at[timestamp]
        except KeyError:
            return default
        return float(half_life) if not np.isnan(half_life) else default

    def as_series(self) -> pd.Series:
        """Returns the shifted half-life series."""
        return self._half_life
