"""
src/backtest_engine/portfolio_layer/execution/strategy_runner.py

Per-slot strategy instance management and signal collection.

Responsibility: For each StrategySlot, maintains one strategy instance per
symbol (built via LegacyStrategyAdapter), calls on_bar(), and translates
returned Orders into StrategySignals.  No sizing logic here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import pandas as pd

from src.backtest_engine.execution import Order
from ..domain.contracts import PortfolioConfig
from ..domain.signals import RequestedOrderIntent, StrategySignal
from ..adapters.legacy_strategy_adapter import LegacyStrategyAdapter


class StrategyRunner:
    """
    Manages one strategy instance per (slot_id, symbol) pair.

    Methodology:
        Strategies are constructed once before the bar loop via
        LegacyStrategyAdapter.build() — see that module for explicit
        limitations of the legacy BaseStrategy adapter contract.

        on_bar() returns List[Order]. StrategyRunner preserves two layers of
        information:
          1. Allocator-compatible directional state (`StrategySignal.direction`)
             extracted from the legacy invested-state flags.
          2. Raw execution intent copied from the full emitted order list. The
             compatibility `requested_*` fields still mirror the last order.

        Sizing is deferred entirely to the Allocator.
    """

    def __init__(
        self,
        config: PortfolioConfig,
        data_map: Dict[Tuple[int, str], pd.DataFrame],
        settings: Any,
    ) -> None:
        """
        Args:
            config: Validated PortfolioConfig.
            data_map: (slot_id, symbol) → full OHLCV DataFrame.
            settings: BacktestSettings instance.
        """
        self._config = config
        self._instances: Dict[Tuple[int, str], Any] = {}

        for slot_id, slot in enumerate(config.slots):
            for symbol in slot.symbols:
                df = data_map.get((slot_id, symbol), pd.DataFrame())
                instance = LegacyStrategyAdapter.build(
                    strategy_class=slot.strategy_class,
                    data=df,
                    symbol=symbol,
                    settings=settings,
                    params=slot.params,
                )
                self._instances[(slot_id, symbol)] = instance

    def collect_signals(
        self,
        bar_map: Dict[Tuple[int, str], Any],
        timestamp: Any,
        current_positions: Optional[Dict[Tuple[int, str], float]] = None,
    ) -> List[StrategySignal]:
        """
        Calls on_bar() for every (slot_id, symbol) and collects signals.

        Args:
            bar_map: (slot_id, symbol) → current OHLCV bar Series.
            timestamp: Current bar timestamp (close[t]).
            current_positions: Optional real book positions keyed by
                (slot_id, symbol). When provided, the runner mirrors them into
                each legacy strategy's mock portfolio before on_bar().

        Returns:
            List of StrategySignal objects.
        """
        signals: List[StrategySignal] = []

        for (slot_id, symbol), instance in self._instances.items():
            bar = bar_map.get((slot_id, symbol))
            if bar is None:
                continue
            self._sync_mock_portfolio_state(
                slot_id=slot_id,
                symbol=symbol,
                instance=instance,
                current_positions=current_positions,
            )

            try:
                orders: List[Order] = instance.on_bar(bar) or []
            except Exception as exc:
                print(f"[Runner] {instance.__class__.__name__}({symbol}) error: {exc}")
                orders = []

            if not orders:
                continue

            requested_orders = self._build_requested_orders(orders)
            order = orders[-1]
            signals.append(self._build_signal(
                slot_id=slot_id,
                symbol=symbol,
                instance=instance,
                order=order,
                requested_orders=requested_orders,
                timestamp=timestamp,
            ))

        return signals

    def reset_runtime_state(self) -> None:
        """
        Clears legacy runtime flags after forced liquidation-style events.
        """
        for instance in self._instances.values():
            if hasattr(instance, "_invested"):
                instance._invested = False
            if hasattr(instance, "_position_side"):
                instance._position_side = None
            if hasattr(instance, "_awaiting_entry"):
                instance._awaiting_entry = False
            if hasattr(instance, "_exit_session_date"):
                instance._exit_session_date = None
            if hasattr(instance, "_entry_signal_date"):
                instance._entry_signal_date = None

    @staticmethod
    def _sync_mock_portfolio_state(
        slot_id: int,
        symbol: str,
        instance: Any,
        current_positions: Optional[Dict[Tuple[int, str], float]],
    ) -> None:
        """
        Mirrors the real slot exposure into the legacy strategy's mock engine.

        This keeps BaseStrategy.get_position()/is_flat() aligned with the
        portfolio book even though the adapter still exposes only a thin mock
        portfolio view rather than full portfolio context.
        """
        if current_positions is None:
            return
        engine = getattr(instance, "engine", None)
        portfolio = getattr(engine, "portfolio", None)
        positions = getattr(portfolio, "positions", None)
        if not isinstance(positions, dict):
            return
        positions[symbol] = float(current_positions.get((slot_id, symbol), 0.0))

    @staticmethod
    def _build_signal(
        slot_id: int,
        symbol: str,
        instance: Any,
        order: Order,
        requested_orders: Tuple[RequestedOrderIntent, ...],
        timestamp: Any,
    ) -> StrategySignal:
        """
        Builds a StrategySignal that preserves both target-direction state and
        the raw execution intent emitted by the legacy strategy order.

        Bridge note:
            Direction still comes from private legacy flags because the
            strategy contract has not been retired yet. Keep this dependency
            explicit so future refactors do not mistake it for incidental state.
        """
        if getattr(instance, "_invested", False):
            pos_side = getattr(instance, "_position_side", None)
            if pos_side == "LONG":
                direction = 1
            elif pos_side == "SHORT":
                direction = -1
            else:
                direction = 0
        else:
            direction = 0

        return StrategySignal(
            slot_id=slot_id,
            symbol=symbol,
            direction=direction,
            reason=order.reason,
            timestamp=timestamp,
            requested_order_id=order.id,
            requested_side=order.side,
            requested_quantity=float(order.quantity),
            requested_order_type=str(order.order_type).upper(),
            requested_limit_price=(
                None if order.limit_price is None else float(order.limit_price)
            ),
            requested_stop_price=(
                None if order.stop_price is None else float(order.stop_price)
            ),
            requested_time_in_force=str(order.time_in_force).upper(),
            requested_reduce_only=bool(order.reduce_only),
            requested_orders=requested_orders,
        )

    @staticmethod
    def _build_requested_orders(
        orders: List[Order],
    ) -> Tuple[RequestedOrderIntent, ...]:
        """
        Preserves the full raw order set emitted on a strategy bar.

        Methodology:
            When a strategy emits multiple reduce-only non-market exit orders on
            the same bar, they are treated as a protective bracket candidate
            and assigned a shared OCO group identifier.
        """
        protective_indexes = [
            index
            for index, order in enumerate(orders)
            if bool(order.reduce_only) and str(order.order_type).upper() != "MARKET"
        ]
        oco_group_id = uuid4().hex if len(protective_indexes) >= 2 else None
        requested_orders: List[RequestedOrderIntent] = []

        for index, order in enumerate(orders):
            is_protective = index in protective_indexes
            requested_orders.append(
                RequestedOrderIntent(
                    order_id=order.id,
                    side=str(order.side).upper(),
                    quantity=float(order.quantity),
                    order_type=str(order.order_type).upper(),
                    reason=order.reason,
                    limit_price=(
                        None if order.limit_price is None else float(order.limit_price)
                    ),
                    stop_price=(
                        None if order.stop_price is None else float(order.stop_price)
                    ),
                    time_in_force=str(order.time_in_force).upper(),
                    reduce_only=bool(order.reduce_only),
                    oco_group_id=oco_group_id if is_protective else None,
                    oco_role=(
                        StrategyRunner._infer_oco_role(order)
                        if oco_group_id is not None and is_protective
                        else None
                    ),
                )
            )

        return tuple(requested_orders)

    @staticmethod
    def _infer_oco_role(order: Order) -> str:
        """
        Maps a protective raw order into a coarse OCO role.
        """
        order_type = str(order.order_type).upper()
        if order_type in {"STOP", "STOP_LIMIT"}:
            return "STOP"
        return "TARGET"
