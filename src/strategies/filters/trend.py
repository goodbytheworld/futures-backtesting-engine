"""
Trend-related trade filters.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class TrendFilter:
    """
    Blocks mean-reversion entries during statistically strong trends.

    Methodology:
        A rolling OLS slope T-statistic is estimated from price versus a simple
        time index. Large absolute values imply a persistent directional trend,
        making counter-trend entries less attractive.
    """

    def __init__(
        self,
        price: pd.Series,
        window: int,
        max_t_stat: float = 2.0,
    ) -> None:
        """
        Initializes the trend filter.

        Args:
            price: Close-price series indexed by timestamp.
            window: Rolling regression window.
            max_t_stat: Maximum allowed absolute T-statistic.
        """
        self.max_t_stat = max_t_stat
        trend_index = pd.Series(np.arange(len(price)), index=price.index)

        cov_st = price.rolling(window=window, min_periods=window // 2).cov(trend_index)
        var_t = trend_index.rolling(window=window, min_periods=window // 2).var()
        slope = cov_st / var_t
        intercept = (
            price.rolling(window=window, min_periods=window // 2).mean()
            - slope * trend_index.rolling(window=window, min_periods=window // 2).mean()
        )
        residual = price - (intercept + slope * trend_index)
        res_var = residual.rolling(window=window, min_periods=window // 2).var()
        se_slope = np.sqrt(np.maximum(res_var / ((window - 1) * var_t), 0.0))
        self._t_stat: pd.Series = (slope / se_slope).shift(1)

    def is_allowed(self, timestamp: object) -> bool:
        """
        Returns whether the trend T-statistic remains below the threshold.

        Args:
            timestamp: Bar index label to query.

        Returns:
            ``True`` when the completed trend signal is weak enough.
        """
        try:
            value = self._t_stat.at[timestamp]
        except KeyError:
            return True
        if np.isnan(value):
            return True
        return abs(value) < self.max_t_stat

    def as_series(self) -> pd.Series:
        """Returns the shifted T-statistic series."""
        return self._t_stat
