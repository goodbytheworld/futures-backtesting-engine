"""
Strategies package.

Available strategies:
  IctOrderBlockStrategy — 3-candle SMC order block logic with Trend/Vol filters.
  SmaPullbackStrategy — Trend following with SMA pullback entries.
  ThreeBarMeanReversionStrategy — 3-bar mean reversion with daily regime filter.

Reusable components in filters.py:
  VolatilityRegimeFilter, TrendFilter, ADFFilter, KalmanBeta.
"""
