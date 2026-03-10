from __future__ import annotations

import pandas as pd
import numpy as np

from src.backtest_engine.analytics.metrics import calc_dsr


def test_calc_dsr_uses_return_sample_not_external_sharpe_input() -> None:
    """
    DSR should be driven by the observed return sample, not by an arbitrary
    externally supplied Sharpe estimate.
    """
    rng = np.random.default_rng(7)
    returns = pd.Series(rng.normal(0.001, 0.01, 252))

    dsr_low = calc_dsr(returns, sharpe=0.0)
    dsr_high = calc_dsr(returns, sharpe=25.0)

    assert 0.0 <= dsr_low <= 1.0
    assert 0.0 <= dsr_high <= 1.0
    assert abs(dsr_low - dsr_high) < 1e-12


def test_calc_dsr_penalizes_multiple_testing() -> None:
    """
    DSR should decrease when the same realised performance is evaluated
    against a broader search of competing trials.
    """
    rng = np.random.default_rng(11)
    returns = pd.Series(rng.normal(0.0012, 0.01, 400))

    dsr_single = calc_dsr(returns, sharpe=0.0, trials=1)
    dsr_many = calc_dsr(
        returns,
        sharpe=0.0,
        trials=50,
        trials_sharpe=[-0.4, -0.1, 0.0, 0.2, 0.35, 0.5, 0.65, 0.9],
    )

    assert 0.0 <= dsr_single <= 1.0
    assert 0.0 <= dsr_many <= 1.0
    assert dsr_many < dsr_single
