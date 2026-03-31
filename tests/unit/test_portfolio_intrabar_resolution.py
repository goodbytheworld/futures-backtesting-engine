"""Phase 10 lower-timeframe intrabar conflict resolution tests."""

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
        intrabar_conflict_resolution="lower_timeframe",
        intrabar_resolution_timeframe="5m",
        **overrides,
    )
    settings.instrument_specs = {"ES": {"tick_size": 1.0, "multiplier": 1.0}}
    return settings


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


def _coarse_conflict_data() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [
            datetime(2025, 1, 1, 9, 30),
            datetime(2025, 1, 1, 10, 0),
            datetime(2025, 1, 1, 10, 30),
            datetime(2025, 1, 1, 11, 0),
        ]
    )
    return pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [100.0, 100.0, 106.0, 100.0],
            "low": [100.0, 100.0, 94.0, 100.0],
            "close": [100.0, 100.0, 100.0, 100.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )


def _intrabar_target_first() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [
            datetime(2025, 1, 1, 10, 5),
            datetime(2025, 1, 1, 10, 10),
            datetime(2025, 1, 1, 10, 15),
            datetime(2025, 1, 1, 10, 20),
            datetime(2025, 1, 1, 10, 25),
            datetime(2025, 1, 1, 10, 30),
        ]
    )
    return pd.DataFrame(
        {
            "open": [100.0, 105.0, 104.0, 94.0, 100.0, 100.0],
            "high": [106.0, 105.0, 104.0, 94.0, 100.0, 100.0],
            "low": [100.0, 104.0, 94.0, 94.0, 100.0, 100.0],
            "close": [105.0, 104.0, 94.0, 100.0, 100.0, 100.0],
            "volume": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )


def _intrabar_stop_first() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [
            datetime(2025, 1, 1, 10, 5),
            datetime(2025, 1, 1, 10, 10),
            datetime(2025, 1, 1, 10, 15),
            datetime(2025, 1, 1, 10, 20),
            datetime(2025, 1, 1, 10, 25),
            datetime(2025, 1, 1, 10, 30),
        ]
    )
    return pd.DataFrame(
        {
            "open": [100.0, 95.0, 96.0, 106.0, 100.0, 100.0],
            "high": [100.0, 96.0, 106.0, 106.0, 100.0, 100.0],
            "low": [94.0, 95.0, 96.0, 100.0, 100.0, 100.0],
            "close": [95.0, 96.0, 106.0, 100.0, 100.0, 100.0],
            "volume": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )


def _intrabar_incomplete() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [
            datetime(2025, 1, 1, 10, 5),
            datetime(2025, 1, 1, 10, 10),
            datetime(2025, 1, 1, 10, 15),
            datetime(2025, 1, 1, 10, 20),
            datetime(2025, 1, 1, 10, 25),
        ]
    )
    return pd.DataFrame(
        {
            "open": [100.0, 105.0, 104.0, 94.0, 100.0],
            "high": [106.0, 105.0, 104.0, 94.0, 100.0],
            "low": [100.0, 104.0, 94.0, 94.0, 100.0],
            "close": [105.0, 104.0, 94.0, 100.0, 100.0],
            "volume": [1.0, 1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )


def _intrabar_interior_gap() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [
            datetime(2025, 1, 1, 10, 5),
            datetime(2025, 1, 1, 10, 10),
            datetime(2025, 1, 1, 10, 20),
            datetime(2025, 1, 1, 10, 25),
            datetime(2025, 1, 1, 10, 30),
        ]
    )
    return pd.DataFrame(
        {
            "open": [100.0, 105.0, 94.0, 100.0, 100.0],
            "high": [106.0, 105.0, 94.0, 100.0, 100.0],
            "low": [100.0, 94.0, 94.0, 100.0, 100.0],
            "close": [105.0, 94.0, 100.0, 100.0, 100.0],
            "volume": [1.0, 1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )


def _wide_bracket_data(close_price: float) -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [
            datetime(2025, 1, 1, 9, 30),
            datetime(2025, 1, 1, 10, 0),
            datetime(2025, 1, 1, 10, 30),
            datetime(2025, 1, 1, 11, 0),
        ]
    )
    return pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, close_price],
            "high": [100.0, 100.0, 100.0, close_price],
            "low": [100.0, 100.0, close_price, close_price],
            "close": [100.0, 100.0, close_price, close_price],
            "volume": [1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )


def test_lower_tf_replay_can_confirm_stop_first() -> None:
    """Lower-TF replay should still choose the stop when it clearly fires first."""
    engine = PortfolioBacktestEngine(config=_config(BracketTargetStrategy), settings=_settings())
    engine._data_map = {(0, "ES"): _coarse_conflict_data()}
    engine._intrabar_data_map = {(0, "ES"): _intrabar_stop_first()}
    engine.run()

    trades = engine._slot_trades[0]
    assert len(trades) == 1
    assert trades[0].exit_reason == "SL"


def test_lower_tf_replay_can_override_pessimistic_stop_when_target_is_first() -> None:
    """If lower-TF replay proves target-first ordering, the target should win."""
    engine = PortfolioBacktestEngine(config=_config(BracketTargetStrategy), settings=_settings())
    engine._data_map = {(0, "ES"): _coarse_conflict_data()}
    engine._intrabar_data_map = {(0, "ES"): _intrabar_target_first()}
    engine.run()

    trades = engine._slot_trades[0]
    assert len(trades) == 1
    assert trades[0].exit_reason == "TP"


def test_missing_lower_tf_data_falls_back_to_pessimistic_stop() -> None:
    """Incomplete lower-TF replay coverage must fall back to coarse-bar pessimism."""
    engine = PortfolioBacktestEngine(config=_config(BracketTargetStrategy), settings=_settings())
    engine._data_map = {(0, "ES"): _coarse_conflict_data()}
    engine._intrabar_data_map = {(0, "ES"): _intrabar_incomplete()}
    engine.run()

    trades = engine._slot_trades[0]
    assert len(trades) == 1
    assert trades[0].exit_reason == "SL"


def test_interior_gap_in_lower_tf_replay_falls_back_to_pessimistic_stop() -> None:
    """Interior replay gaps must not override the default pessimistic policy."""
    engine = PortfolioBacktestEngine(config=_config(BracketTargetStrategy), settings=_settings())
    engine._data_map = {(0, "ES"): _coarse_conflict_data()}
    engine._intrabar_data_map = {(0, "ES"): _intrabar_interior_gap()}
    engine.run()

    trades = engine._slot_trades[0]
    assert len(trades) == 1
    assert trades[0].exit_reason == "SL"


def test_risk_halt_is_unchanged_with_resolver_enabled() -> None:
    """Risk liquidation semantics must remain unchanged when replay is enabled."""
    engine = PortfolioBacktestEngine(
        config=_config(WideBracketStrategy),
        settings=_settings(max_daily_loss=1.0),
    )
    engine._data_map = {(0, "ES"): _wide_bracket_data(close_price=94.0)}
    engine._intrabar_data_map = {(0, "ES"): _intrabar_target_first()}
    engine.run()

    trades = engine._slot_trades[0]
    assert len(trades) == 1
    assert trades[0].exit_reason == "RISK_LIQ"
    assert engine.book.get_position(0, "ES") == 0.0


def test_eod_is_unchanged_with_resolver_enabled() -> None:
    """EOD liquidation semantics must remain unchanged when replay is enabled."""
    engine = PortfolioBacktestEngine(
        config=_config(WideBracketStrategy),
        settings=_settings(eod_close_time="10:30"),
    )
    engine._data_map = {(0, "ES"): _wide_bracket_data(close_price=99.0)}
    engine._intrabar_data_map = {(0, "ES"): _intrabar_target_first()}
    engine.run()

    trades = engine._slot_trades[0]
    assert len(trades) == 1
    assert trades[0].exit_reason == "EOD_CLOSE"
    assert engine.book.get_position(0, "ES") == 0.0


def test_lower_tf_data_is_loaded_only_when_conflict_occurs(monkeypatch) -> None:
    """
    Lower-TF replay data should be loaded lazily only for an actual OCO conflict.
    """
    load_calls: list[tuple[str, str]] = []

    engine = PortfolioBacktestEngine(config=_config(BracketTargetStrategy), settings=_settings())
    engine._data_map = {(0, "ES"): _coarse_conflict_data()}

    def fake_load(symbol: str, timeframe: str, start_date=None, end_date=None) -> pd.DataFrame:
        load_calls.append((symbol, timeframe))
        return _intrabar_target_first()

    monkeypatch.setattr(engine.data_lake, "load", fake_load)

    engine.run()

    trades = engine._slot_trades[0]
    assert len(trades) == 1
    assert trades[0].exit_reason == "TP"
    assert load_calls == [("ES", "5m")]


def test_lower_tf_data_is_not_loaded_without_same_bar_conflict(monkeypatch) -> None:
    """
    A non-conflicting bracket should not trigger lower-TF replay loading.
    """
    load_calls: list[tuple[str, str]] = []

    engine = PortfolioBacktestEngine(config=_config(BracketTargetStrategy), settings=_settings())
    engine._data_map = {
        (0, "ES"): pd.DataFrame(
            {
                "open": [100.0, 100.0, 100.0, 105.0],
                "high": [100.0, 100.0, 105.0, 105.0],
                "low": [100.0, 100.0, 99.0, 105.0],
                "close": [100.0, 100.0, 105.0, 105.0],
                "volume": [1.0, 1.0, 1.0, 1.0],
            },
            index=pd.DatetimeIndex(
                [
                    datetime(2025, 1, 1, 9, 30),
                    datetime(2025, 1, 1, 10, 0),
                    datetime(2025, 1, 1, 10, 30),
                    datetime(2025, 1, 1, 11, 0),
                ]
            ),
        )
    }

    def fake_load(symbol: str, timeframe: str, start_date=None, end_date=None) -> pd.DataFrame:
        load_calls.append((symbol, timeframe))
        return _intrabar_target_first()

    monkeypatch.setattr(engine.data_lake, "load", fake_load)

    engine.run()

    trades = engine._slot_trades[0]
    assert len(trades) == 1
    assert trades[0].exit_reason == "TP"
    assert load_calls == []
