"""Regression tests for portfolio execution-template translation."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.backtest_engine.portfolio_layer.domain.contracts import PortfolioConfig, StrategySlot
from src.backtest_engine.portfolio_layer.engine.engine import PortfolioBacktestEngine
from src.backtest_engine.config import BacktestSettings
from src.strategies.base import BaseStrategy


class OneShotDayLimitEntryStrategy(BaseStrategy):
    """Emits one long DAY limit that should expire unfilled."""

    def __init__(self, engine) -> None:
        super().__init__(engine)
        self._emitted = False

    def on_bar(self, bar) -> list:
        if self._emitted:
            return []

        self._emitted = True
        self._invested = True
        self._position_side = "LONG"
        return [self.limit_order("BUY", 1, limit_price=95.0, reason="SIGNAL", time_in_force="DAY")]


def test_day_limit_expiry_invalidates_target_without_market_requeue() -> None:
    """
    An unfilled DAY limit must die cleanly on the next day instead of becoming
    a stale market delta from the preserved target state.
    """
    index = pd.DatetimeIndex(
        [
            datetime(2025, 1, 1, 9, 30),
            datetime(2025, 1, 1, 10, 0),
            datetime(2025, 1, 2, 9, 30),
            datetime(2025, 1, 2, 10, 0),
        ]
    )
    data = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [101.0, 101.0, 101.0, 101.0],
            "low": [99.0, 99.0, 99.0, 99.0],
            "close": [100.0, 100.0, 100.0, 100.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )

    slot = StrategySlot(
        strategy_class=OneShotDayLimitEntryStrategy,
        symbols=["ES"],
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
        use_trading_hours=False,
    )
    settings.instrument_specs = {"ES": {"tick_size": 1.0, "multiplier": 1.0}}

    engine = PortfolioBacktestEngine(config=config, settings=settings)
    engine._data_map = {(0, "ES"): data}
    engine.run()

    assert engine.book.get_position(0, "ES") == 0.0
    assert engine._slot_trades[0] == []
