"""
Strategies package.

Available strategies:
  SmaCrossoverStrategy  — Dual SMA trend following with ATR-scaled SL/TP.
  MeanReversionStrategy — RSI + Bollinger Bands with optional regime filters.
  IctOrderBlockStrategy — 3-candle SMC order block logic with Trend/Vol filters.
  ZScoreReversalStrategy — Z-Score based mean-reversion with stationarity filters.

Reusable components in filters.py:
  VolatilityRegimeFilter, TrendFilter, ADFFilter, KalmanBeta.
"""

