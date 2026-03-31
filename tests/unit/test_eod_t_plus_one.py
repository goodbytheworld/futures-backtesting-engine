"""Regression tests for t+1 eligibility around forced EOD handling."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.backtest_engine.single_asset import BacktestEngine
from src.backtest_engine.portfolio_layer.domain.contracts import PortfolioConfig, StrategySlot
from src.backtest_engine.portfolio_layer.engine.engine import PortfolioBacktestEngine
from src.backtest_engine.config import BacktestSettings
from src.strategies.base import BaseStrategy


class SingleEngineEodEntryStrategy(BaseStrategy):
    """Emits a one-shot market entry exactly on the EOD bar."""

    def __init__(self, engine) -> None:
        super().__init__(engine)
        self._emitted = False

    def on_bar(self, bar) -> list:
        if self._emitted or bar.name.time() != datetime(2025, 1, 1, 10, 30).time():
            return []
        self._emitted = True
        self._invested = True
        self._position_side = "LONG"
        return [self.market_order("BUY", 1, reason="SIGNAL")]


class PortfolioEodEntryStrategy(BaseStrategy):
    """Emits a one-shot market entry exactly on the EOD bar."""

    def __init__(self, engine) -> None:
        super().__init__(engine)
        self._emitted = False

    def on_bar(self, bar) -> list:
        if self._emitted or bar.name.time() != datetime(2025, 1, 1, 10, 30).time():
            return []
        self._emitted = True
        self._invested = True
        self._position_side = "LONG"
        return [self.market_order("BUY", 1, reason="SIGNAL")]


def _market_data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [100.0, 101.0, 102.0, 103.0, 104.0],
            "low": [100.0, 101.0, 102.0, 103.0, 104.0],
            "close": [100.0, 101.0, 102.0, 103.0, 104.0],
            "volume": [1.0, 1.0, 1.0, 1.0, 1.0],
        },
        index=pd.DatetimeIndex(
            [
                datetime(2025, 1, 1, 9, 30),
                datetime(2025, 1, 1, 10, 0),
                datetime(2025, 1, 1, 10, 30),
                datetime(2025, 1, 2, 9, 30),
                datetime(2025, 1, 2, 10, 0),
            ]
        ),
    )


def test_single_engine_eod_does_not_execute_fresh_same_bar_order() -> None:
    """A bar[t] signal on the EOD bar must not be force-filled on that same bar."""
    data = _market_data()
    settings = BacktestSettings(
        commission_rate=0.0,
        spread_ticks=0,
        initial_capital=10_000.0,
        use_trading_hours=False,
        eod_close_time="10:30",
    )
    settings.default_symbol = "ES"
    settings.instrument_specs = {"ES": {"tick_size": 1.0, "multiplier": 1.0}}

    engine = BacktestEngine(settings=settings, data=data)
    engine.run(SingleEngineEodEntryStrategy)

    assert engine.portfolio.positions.get("ES", 0.0) == 0.0
    assert engine.execution.trades == []
    assert engine.execution.fills == []


def test_portfolio_engine_eod_does_not_execute_fresh_same_bar_order() -> None:
    """A portfolio bar[t] signal on the EOD bar must not be force-filled on that same bar."""
    data = _market_data()
    slot = StrategySlot(
        strategy_class=PortfolioEodEntryStrategy,
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
        eod_close_time="10:30",
    )
    settings.instrument_specs = {"ES": {"tick_size": 1.0, "multiplier": 1.0}}

    engine = PortfolioBacktestEngine(config=config, settings=settings)
    engine._data_map = {(0, "ES"): data}
    engine.run()

    assert engine.book.get_position(0, "ES") == 0.0
    assert engine._slot_trades[0] == []
