"""tests/regression/test_exit_signals.py

Regression: SELL from a flat strategy should produce direction=-1 (short intent),
not be silently treated as an exit.  Previously SELL→-1 always, but the distinction
of intent vs. book-delta is the Allocator+Engine's job, NOT the runner's.
"""

import pytest
import pandas as pd

from src.backtest_engine.portfolio_layer.execution.strategy_runner import StrategyRunner
from src.backtest_engine.portfolio_layer.domain.contracts import PortfolioConfig, StrategySlot
from src.backtest_engine.config import BacktestSettings
from src.strategies.base import BaseStrategy


class _AlwaysSell:
    """Minimal strategy that always emits a SELL order."""
    def __init__(self, engine):
        self._invested = True
        self._position_side = "SHORT"

    def on_bar(self, bar):
        from src.backtest_engine.execution import Order
        return [Order(symbol="ES", quantity=1, side="SELL",
                      order_type="MARKET", reason="TEST", timestamp=None)]


class _AlwaysBuy:
    """Minimal strategy that always emits a BUY order."""
    def __init__(self, engine):
        self._invested = True
        self._position_side = "LONG"

    def on_bar(self, bar):
        from src.backtest_engine.execution import Order
        return [Order(symbol="ES", quantity=1, side="BUY",
                      order_type="MARKET", reason="TEST", timestamp=None)]


class _LimitExit:
    """Minimal strategy that emits a resting exit order with raw metadata."""
    def __init__(self, engine):
        self._invested = False
        self._position_side = None

    def on_bar(self, bar):
        from src.backtest_engine.execution import Order
        return [Order(
            symbol="ES",
            quantity=2,
            side="SELL",
            order_type="LIMIT",
            limit_price=4012.5,
            reason="TP",
            time_in_force="GTC",
            reduce_only=True,
            timestamp=None,
        )]


class _BracketExit:
    """Minimal strategy that emits a stop/target protective bracket."""
    def __init__(self, engine):
        self._invested = True
        self._position_side = "LONG"

    def on_bar(self, bar):
        from src.backtest_engine.execution import Order
        return [
            Order(
                symbol="ES",
                quantity=1,
                side="SELL",
                order_type="STOP",
                stop_price=3990.0,
                reason="SL",
                time_in_force="GTC",
                reduce_only=True,
                timestamp=None,
            ),
            Order(
                symbol="ES",
                quantity=1,
                side="SELL",
                order_type="LIMIT",
                limit_price=4015.0,
                reason="TP",
                time_in_force="GTC",
                reduce_only=True,
                timestamp=None,
            ),
        ]


class _UsesBaseStrategyPosition(BaseStrategy):
    """Confirms that BaseStrategy position helpers see the real portfolio book."""

    def on_bar(self, bar):
        from src.backtest_engine.execution import Order

        current_qty = self.get_position()
        if current_qty == 2.0:
            self._invested = True
            self._position_side = "LONG"
            return [Order(symbol="ES", quantity=1, side="SELL", order_type="MARKET", reason="SYNC_OK")]
        return []


def _make_config(strategy_class):
    return PortfolioConfig(
        slots=[StrategySlot(strategy_class=strategy_class, symbols=["ES"], weight=1.0)],
        initial_capital=100_000.0,
        rebalance_frequency="intrabar",
    )


def _make_data() -> pd.DataFrame:
    idx = pd.date_range("2023-01-02 09:30", periods=5, freq="30min")
    return pd.DataFrame(
        {"open": 4000.0, "high": 4010.0, "low": 3990.0, "close": 4005.0, "volume": 1000},
        index=idx,
    )


class TestExitSignalMapping:
    def test_sell_from_flat_maps_to_minus_one(self):
        """SELL → direction -1.  The engine decides whether it's a reversal or exit."""
        settings = BacktestSettings()
        df = _make_data()
        config = _make_config(_AlwaysSell)
        data_map = {(0, "ES"): df}

        runner = StrategyRunner(config, data_map, settings)
        ts = df.index[0]
        bar_map = {(0, "ES"): df.loc[ts]}
        signals = runner.collect_signals(bar_map, ts)

        assert len(signals) == 1
        assert signals[0].direction == -1

    def test_buy_maps_to_plus_one(self):
        settings = BacktestSettings()
        df = _make_data()
        config = _make_config(_AlwaysBuy)
        data_map = {(0, "ES"): df}

        runner = StrategyRunner(config, data_map, settings)
        ts = df.index[0]
        bar_map = {(0, "ES"): df.loc[ts]}
        signals = runner.collect_signals(bar_map, ts)

        assert len(signals) == 1
        assert signals[0].direction == 1

    def test_no_orders_yields_no_signal(self):
        class _Silent:
            def __init__(self, engine): pass
            def on_bar(self, bar): return []

        settings = BacktestSettings()
        df = _make_data()
        config = _make_config(_Silent)
        data_map = {(0, "ES"): df}

        runner = StrategyRunner(config, data_map, settings)
        ts = df.index[0]
        bar_map = {(0, "ES"): df.loc[ts]}
        signals = runner.collect_signals(bar_map, ts)

        assert signals == []

    def test_signal_preserves_raw_order_metadata(self):
        settings = BacktestSettings()
        df = _make_data()
        config = _make_config(_LimitExit)
        data_map = {(0, "ES"): df}

        runner = StrategyRunner(config, data_map, settings)
        ts = df.index[0]
        bar_map = {(0, "ES"): df.loc[ts]}
        signals = runner.collect_signals(bar_map, ts)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.direction == 0
        assert signal.reason == "TP"
        assert signal.requested_side == "SELL"
        assert signal.requested_quantity == 2.0
        assert signal.requested_order_type == "LIMIT"
        assert signal.requested_limit_price == 4012.5
        assert signal.requested_stop_price is None
        assert signal.requested_time_in_force == "GTC"
        assert signal.requested_reduce_only is True
        assert signal.requested_order_id is not None

    def test_signal_preserves_full_requested_order_set_for_brackets(self):
        settings = BacktestSettings()
        df = _make_data()
        config = _make_config(_BracketExit)
        data_map = {(0, "ES"): df}

        runner = StrategyRunner(config, data_map, settings)
        ts = df.index[0]
        bar_map = {(0, "ES"): df.loc[ts]}
        signals = runner.collect_signals(bar_map, ts)

        assert len(signals) == 1
        signal = signals[0]
        assert len(signal.requested_orders) == 2
        assert {order.reason for order in signal.requested_orders} == {"SL", "TP"}
        assert all(order.reduce_only for order in signal.requested_orders)
        assert signal.requested_orders[0].oco_group_id is not None
        assert signal.requested_orders[0].oco_group_id == signal.requested_orders[1].oco_group_id
        assert {order.oco_role for order in signal.requested_orders} == {"STOP", "TARGET"}

    def test_runner_syncs_real_book_position_into_legacy_base_strategy_helpers(self):
        settings = BacktestSettings()
        df = _make_data()
        config = _make_config(_UsesBaseStrategyPosition)
        data_map = {(0, "ES"): df}

        runner = StrategyRunner(config, data_map, settings)
        ts = df.index[0]
        bar_map = {(0, "ES"): df.loc[ts]}
        signals = runner.collect_signals(
            bar_map,
            ts,
            current_positions={(0, "ES"): 2.0},
        )

        assert len(signals) == 1
        assert signals[0].reason == "SYNC_OK"
        assert signals[0].direction == 1
