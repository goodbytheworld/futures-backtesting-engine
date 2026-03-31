"""Phase 9 portfolio OMS regression tests."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.backtest_engine.portfolio_layer.domain.contracts import PortfolioConfig, StrategySlot
from src.backtest_engine.portfolio_layer.engine.engine import PortfolioBacktestEngine
from src.backtest_engine.config import BacktestSettings
from src.strategies.base import BaseStrategy


def _config(strategy_class: type[BaseStrategy]) -> PortfolioConfig:
    return PortfolioConfig(
        slots=[
            StrategySlot(
                strategy_class=strategy_class,
                symbols=["ES"],
                weight=1.0,
                timeframe="30m",
            )
        ],
        initial_capital=10_000.0,
        rebalance_frequency="intrabar",
        target_portfolio_vol=0.10,
        max_contracts_per_slot=1,
    )


def _settings(**overrides) -> BacktestSettings:
    settings = BacktestSettings(
        commission_rate=0.0,
        spread_ticks=0,
        use_trading_hours=False,
        **overrides,
    )
    settings.instrument_specs = {"ES": {"tick_size": 1.0, "multiplier": 1.0}}
    return settings


class ReplaceRestingLimitStrategy(BaseStrategy):
    """Emits a second entry limit that should explicitly replace the first."""

    def __init__(self, engine) -> None:
        super().__init__(engine)
        self.calls = 0

    def on_bar(self, bar) -> list:
        self.calls += 1
        self._invested = True
        self._position_side = "LONG"
        if self.calls == 1:
            return [self.limit_order("BUY", 1, limit_price=95.0, reason="SIGNAL", time_in_force="GTC")]
        if self.calls == 2:
            return [self.limit_order("BUY", 1, limit_price=99.0, reason="SIGNAL", time_in_force="GTC")]
        return []


class BracketTargetStrategy(BaseStrategy):
    """Enters long once, then emits a reduce-only stop/target bracket."""

    def __init__(self, engine) -> None:
        super().__init__(engine)
        self.calls = 0

    def on_bar(self, bar) -> list:
        self.calls += 1
        if self.calls == 1:
            self._invested = True
            self._position_side = "LONG"
            return [self.market_order("BUY", 1, reason="SIGNAL")]
        if self.calls == 2:
            self._invested = True
            self._position_side = "LONG"
            return [
                self.stop_order("SELL", 1, stop_price=95.0, reason="SL", reduce_only=True),
                self.limit_order("SELL", 1, limit_price=105.0, reason="TP", reduce_only=True),
            ]
        return []


class WideBracketStrategy(BaseStrategy):
    """Enters long once, then emits a wide bracket that should remain resting."""

    def __init__(self, engine) -> None:
        super().__init__(engine)
        self.calls = 0

    def on_bar(self, bar) -> list:
        self.calls += 1
        if self.calls == 1:
            self._invested = True
            self._position_side = "LONG"
            return [self.market_order("BUY", 1, reason="SIGNAL")]
        if self.calls == 2:
            self._invested = True
            self._position_side = "LONG"
            return [
                self.stop_order("SELL", 1, stop_price=80.0, reason="SL", reduce_only=True),
                self.limit_order("SELL", 1, limit_price=110.0, reason="TP", reduce_only=True),
            ]
        return []


def test_fresh_signal_replaces_resting_limit_template() -> None:
    """A fresh templated signal must replace the older resting non-market intent."""
    index = pd.DatetimeIndex(
        [
            datetime(2025, 1, 1, 9, 30),
            datetime(2025, 1, 1, 10, 0),
            datetime(2025, 1, 1, 10, 30),
            datetime(2025, 1, 1, 11, 0),
        ]
    )
    data = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [100.0, 101.0, 101.0, 100.0],
            "low": [100.0, 99.0, 98.0, 100.0],
            "close": [100.0, 100.0, 100.0, 100.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )

    engine = PortfolioBacktestEngine(config=_config(ReplaceRestingLimitStrategy), settings=_settings())
    engine._data_map = {(0, "ES"): data}
    engine.run()

    fills = engine._execution_handlers[0].fills
    assert len(fills) == 1
    assert fills[0].order.order_type == "LIMIT"
    assert fills[0].order.limit_price == 99.0
    assert engine.book.get_position(0, "ES") == 1.0


def test_protective_target_fill_cancels_stop_sibling_and_keeps_book_flat() -> None:
    """An OCO target fill must cancel the protective stop sibling and retire the target."""
    index = pd.DatetimeIndex(
        [
            datetime(2025, 1, 1, 9, 30),
            datetime(2025, 1, 1, 10, 0),
            datetime(2025, 1, 1, 10, 30),
            datetime(2025, 1, 1, 11, 0),
        ]
    )
    data = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 104.0],
            "high": [100.0, 100.0, 106.0, 104.0],
            "low": [100.0, 100.0, 99.0, 104.0],
            "close": [100.0, 100.0, 104.0, 104.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )

    engine = PortfolioBacktestEngine(config=_config(BracketTargetStrategy), settings=_settings())
    engine._data_map = {(0, "ES"): data}
    engine.run()

    trades = engine._slot_trades[0]
    assert len(trades) == 1
    assert trades[0].exit_reason == "TP"
    assert engine.book.get_position(0, "ES") == 0.0


def test_same_bar_stop_target_conflict_uses_pessimistic_stop() -> None:
    """If stop and target are both reachable in one bar, the stop must win."""
    index = pd.DatetimeIndex(
        [
            datetime(2025, 1, 1, 9, 30),
            datetime(2025, 1, 1, 10, 0),
            datetime(2025, 1, 1, 10, 30),
            datetime(2025, 1, 1, 11, 0),
        ]
    )
    data = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 95.0],
            "high": [100.0, 100.0, 106.0, 95.0],
            "low": [100.0, 100.0, 94.0, 95.0],
            "close": [100.0, 100.0, 95.0, 95.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )

    engine = PortfolioBacktestEngine(config=_config(BracketTargetStrategy), settings=_settings())
    engine._data_map = {(0, "ES"): data}
    engine.run()

    trades = engine._slot_trades[0]
    assert len(trades) == 1
    assert trades[0].exit_reason == "SL"
    assert trades[0].exit_price == 95.0
    assert engine.book.get_position(0, "ES") == 0.0


def test_risk_halt_cancels_active_bracket_and_liquidates_position() -> None:
    """Risk liquidation must supersede any active bracket-style resting orders."""
    index = pd.DatetimeIndex(
        [
            datetime(2025, 1, 1, 9, 30),
            datetime(2025, 1, 1, 10, 0),
            datetime(2025, 1, 1, 10, 30),
            datetime(2025, 1, 1, 11, 0),
        ]
    )
    data = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 94.0],
            "high": [100.0, 100.0, 100.0, 94.0],
            "low": [100.0, 100.0, 94.0, 94.0],
            "close": [100.0, 100.0, 94.0, 94.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )

    engine = PortfolioBacktestEngine(
        config=_config(WideBracketStrategy),
        settings=_settings(max_daily_loss=1.0),
    )
    engine._data_map = {(0, "ES"): data}
    engine.run()

    trades = engine._slot_trades[0]
    assert len(trades) == 1
    assert trades[0].exit_reason == "RISK_LIQ"
    assert engine.book.get_position(0, "ES") == 0.0


def test_eod_close_cancels_active_bracket_and_flattens_position() -> None:
    """Forced EOD close must cancel active bracket siblings before liquidation."""
    index = pd.DatetimeIndex(
        [
            datetime(2025, 1, 1, 9, 30),
            datetime(2025, 1, 1, 10, 0),
            datetime(2025, 1, 1, 10, 30),
            datetime(2025, 1, 1, 11, 0),
        ]
    )
    data = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 99.0],
            "high": [100.0, 100.0, 100.0, 99.0],
            "low": [100.0, 100.0, 99.0, 99.0],
            "close": [100.0, 100.0, 99.0, 99.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )

    engine = PortfolioBacktestEngine(
        config=_config(WideBracketStrategy),
        settings=_settings(eod_close_time="10:30"),
    )
    engine._data_map = {(0, "ES"): data}
    engine.run()

    trades = engine._slot_trades[0]
    assert len(trades) == 1
    assert trades[0].exit_reason == "EOD_CLOSE"
    assert engine.book.get_position(0, "ES") == 0.0
