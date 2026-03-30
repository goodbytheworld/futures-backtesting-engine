"""
Kalman-filter-based hedge-ratio estimation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit


@njit(fastmath=True)
def _kalman_beta_loop(
    x: np.ndarray,
    y: np.ndarray,
    n: int,
    q_var: float,
    r_var: float,
) -> np.ndarray:
    """
    Runs a lightweight 2D Kalman filter for rolling beta estimation.

    Args:
        x: Independent variable array.
        y: Dependent variable array.
        n: Number of observations.
        q_var: Process noise variance.
        r_var: Measurement noise variance.

    Returns:
        NumPy array of beta estimates aligned to the inputs.
    """
    beta_arr = np.zeros(n)
    alpha, beta = 0.0, 1.0
    p00, p01, p10, p11 = 1.0, 0.0, 0.0, 1.0

    for idx in range(n):
        x_value = x[idx]
        y_value = y[idx]

        p00 += q_var
        p11 += q_var

        innovation_cov = p00 + x_value * (p10 + p01) + x_value * x_value * p11 + r_var
        k0 = (p00 + p01 * x_value) / innovation_cov
        k1 = (p10 + p11 * x_value) / innovation_cov

        error = y_value - (alpha + beta * x_value)
        alpha += k0 * error
        beta += k1 * error

        next_p00 = p00 - (k0 * p00 + k0 * x_value * p10)
        next_p01 = p01 - (k0 * p01 + k0 * x_value * p11)
        next_p10 = p10 - (k1 * p00 + k1 * x_value * p10)
        next_p11 = p11 - (k1 * p01 + k1 * x_value * p11)
        p00, p01, p10, p11 = next_p00, next_p01, next_p10, next_p11

        beta_arr[idx] = beta

    return beta_arr


class KalmanBeta:
    """
    Estimates a dynamic hedge ratio for two co-moving price series.

    Methodology:
        Inputs are aligned to a shared index and scaled to unit magnitude so
        the Kalman noise parameters remain numerically stable across symbols
        with very different price levels.
    """

    def __init__(
        self,
        x: pd.Series,
        y: pd.Series,
        q_var: float = 1e-5,
        r_var: float = 1e-1,
        **legacy_kwargs: float,
    ) -> None:
        """
        Initializes the Kalman beta estimator.

        Args:
            x: Independent-variable price series.
            y: Dependent-variable price series.
            q_var: Process noise variance.
            r_var: Measurement noise variance.
            **legacy_kwargs: Backward-compatible aliases ``Q`` and ``R``.
        """
        if "Q" in legacy_kwargs:
            q_var = float(legacy_kwargs["Q"])
        if "R" in legacy_kwargs:
            r_var = float(legacy_kwargs["R"])

        common_idx = x.index.intersection(y.index)
        x_values = x.loc[common_idx].values.astype(float)
        y_values = y.loc[common_idx].values.astype(float)

        scale = float(x_values[0]) if len(x_values) > 0 and x_values[0] != 0 else 1.0
        beta_arr = _kalman_beta_loop(
            x_values / scale,
            y_values / scale,
            len(x_values),
            q_var,
            r_var,
        )
        self._beta: pd.Series = pd.Series(beta_arr, index=common_idx).shift(1)

    def get(self, timestamp: object, default: float = 1.0) -> float:
        """
        Returns the shifted beta estimate for a bar.

        Args:
            timestamp: Bar index label to query.
            default: Fallback value when no estimate is available.

        Returns:
            Hedge-ratio estimate or ``default``.
        """
        try:
            value = self._beta.at[timestamp]
        except KeyError:
            return default
        return default if np.isnan(value) else float(value)

    def as_series(self) -> pd.Series:
        """Returns the shifted beta series."""
        return self._beta
