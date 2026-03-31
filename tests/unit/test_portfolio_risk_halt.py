"""Regression tests for portfolio risk-halt invalidation semantics."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.backtest_engine.portfolio_layer.domain.contracts import PortfolioConfig, StrategySlot
from src.backtest_engine.portfolio_layer.engine.engine import PortfolioBacktestEngine
from src.backtest_engine.config import BacktestSettings
from src.strategies.base import BaseStrategy


class OneShotPortfolioEntryStrategy(BaseStrategy):
    """Emits a single long intent and never reissues signals."""

    def __init__(self, engine) -> None:
        super().__init__(engine)
        self._emitted = False

    def on_bar(self, bar) -> list:
        if not self._emitted:
            self._emitted = True
            self._invested = True
            self._position_side = "LONG"
            return [self.market_order("BUY", 1, reason="SIGNAL")]
        return []


def test_portfolio_risk_halt_clears_targets_and_prevents_reopen() -> None:
    """Risk liquidation must invalidate stale targets so the next day stays flat."""
    index = pd.DatetimeIndex(
        [
            datetime(2025, 1, 1, 9, 30),
            datetime(2025, 1, 1, 10, 0),
            datetime(2025, 1, 2, 9, 30),
            datetime(2025, 1, 2, 10, 0),
            datetime(2025, 1, 2, 10, 30),
        ]
    )
    data = pd.DataFrame(
        {
            "open": [100.0, 100.0, 99.0, 99.0, 99.0],
            "high": [100.0, 100.0, 99.0, 99.0, 99.0],
            "low": [100.0, 90.0, 99.0, 99.0, 99.0],
            "close": [100.0, 90.0, 99.0, 99.0, 99.0],
            "volume": [1.0, 1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )

    slot = StrategySlot(
        strategy_class=OneShotPortfolioEntryStrategy,
        symbols=["NQ"],
        weight=1.0,
        timeframe="30m",
    )
    config = PortfolioConfig(
        slots=[slot],
        initial_capital=10_000.0,
        rebalance_frequency="intrabar",
        target_portfolio_vol=0.10,
    )
    settings = BacktestSettings(
        commission_rate=0.0,
        spread_ticks=0,
        max_daily_loss=5.0,
        eod_close_time="10:30",
        use_trading_hours=False,
    )
    settings.instrument_specs = {"NQ": {"tick_size": 1.0, "multiplier": 1.0}}

    engine = PortfolioBacktestEngine(config=config, settings=settings)
    engine._data_map = {(0, "NQ"): data}
    engine.run()

    assert engine.book.get_position(0, "NQ") == 0.0
    slot_trades = engine._slot_trades[0]
    assert len(slot_trades) == 1
    assert slot_trades[0].exit_reason == "RISK_LIQ"
