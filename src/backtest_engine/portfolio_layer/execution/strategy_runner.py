"""
src/backtest_engine/portfolio_layer/execution/strategy_runner.py

Per-slot strategy instance management and signal collection.

Responsibility: For each StrategySlot, maintains one strategy instance per
symbol (built via LegacyStrategyAdapter), calls on_bar(), and translates
returned Orders into StrategySignals.  No sizing logic here.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.backtest_engine.execution import Order
from src.backtest_engine.execution.brackets import (
    infer_emitted_order_metadata,
)
from ..domain.contracts import PortfolioConfig
from ..domain.signals import (
    BRIDGE_INTENT_CLOSE,
    BRIDGE_INTENT_HOLD,
    BRIDGE_INTENT_OPEN,
    BRIDGE_INTENT_REVERSE,
    RequestedOrderIntent,
    StrategySignal,
)
from ..adapters.legacy_strategy_adapter import LegacyStrategyAdapter

logger = logging.getLogger(__name__)


class StrategyRunner:
    """
    Manages one strategy instance per (slot_id, symbol) pair.

    Methodology:
        Strategies are constructed once before the bar loop via
        LegacyStrategyAdapter.build() — see that module for explicit
        limitations of the legacy BaseStrategy adapter contract.

        on_bar() returns List[Order]. StrategyRunner preserves two layers of
        information:
          1. Allocator-compatible directional state derived from the real slot
             position first, then from raw pending-entry intent while flat.
          2. Raw execution intent copied from the full emitted order list. The
             compatibility `requested_*` fields mirror the inferred primary
             order for the bar rather than blindly taking the last element.

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
            order = self._select_primary_order(orders)
            current_position = (
                0.0
                if current_positions is None
                else float(current_positions.get((slot_id, symbol), 0.0))
            )
            signals.append(self._build_signal(
                slot_id=slot_id,
                symbol=symbol,
                instance=instance,
                order=order,
                requested_orders=requested_orders,
                timestamp=timestamp,
                current_position=current_position,
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
        current_position: float,
    ) -> StrategySignal:
        """
        Builds a StrategySignal that preserves both target-direction state and
        the raw execution intent emitted by the legacy strategy order.

        Bridge note:
            Direction and bridge intent are inferred together from the live
            position plus the emitted raw order batch. This lets the portfolio
            path distinguish HOLD vs CLOSE vs REVERSE instead of overloading
            `direction` alone.
        """
        direction, bridge_intent = StrategyRunner._resolve_signal_mapping(
            instance=instance,
            requested_orders=requested_orders,
            slot_id=slot_id,
            symbol=symbol,
            current_position=current_position,
        )

        return StrategySignal(
            slot_id=slot_id,
            symbol=symbol,
            direction=direction,
            bridge_intent=bridge_intent,
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
    def _resolve_signal_mapping(
        instance: Any,
        requested_orders: Tuple[RequestedOrderIntent, ...],
        slot_id: int,
        symbol: str,
        current_position: float,
    ) -> Tuple[int, str]:
        """
        Resolves portfolio-facing direction and bridge intent.

        Methodology:
            The bridge uses the live portfolio position as its source of truth
            but must still respect explicit opposite-side non-reduce-only exit
            orders from legacy strategies. Those signals become CLOSE by
            default, or REVERSE when the legacy runtime state has already
            flipped to the opposite side on the signal bar.
        """
        strategy_name = instance.__class__.__name__
        current_direction = StrategyRunner._direction_from_signed_position(current_position)
        primary_entry_order = StrategyRunner._select_primary_entry_order(
            requested_orders=requested_orders,
            strategy_name=strategy_name,
            slot_id=slot_id,
            symbol=symbol,
        )

        if current_direction == 0:
            pending_direction = StrategyRunner._direction_from_primary_entry_order(
                primary_entry_order=primary_entry_order,
                strategy_name=strategy_name,
                slot_id=slot_id,
                symbol=symbol,
                requested_orders=requested_orders,
            )
            if getattr(instance, "_invested", False):
                StrategyRunner._warn_on_flat_legacy_state_conflict(
                    instance=instance,
                    pending_direction=pending_direction,
                    strategy_name=strategy_name,
                    slot_id=slot_id,
                    symbol=symbol,
                    current_position=current_position,
                    requested_orders=requested_orders,
                )
            if pending_direction == 0:
                return 0, BRIDGE_INTENT_HOLD
            return pending_direction, BRIDGE_INTENT_OPEN

        if primary_entry_order is None:
            return current_direction, BRIDGE_INTENT_HOLD

        requested_direction = StrategyRunner._direction_from_order_side(
            side=primary_entry_order.side,
            strategy_name=strategy_name,
            slot_id=slot_id,
            symbol=symbol,
            requested_orders=requested_orders,
        )
        if requested_direction == 0:
            return current_direction, BRIDGE_INTENT_HOLD
        if requested_direction == current_direction:
            return current_direction, BRIDGE_INTENT_HOLD
        if StrategyRunner._legacy_state_requests_reversal(instance, current_direction):
            return requested_direction, BRIDGE_INTENT_REVERSE
        return 0, BRIDGE_INTENT_CLOSE

    @staticmethod
    def _resolve_signal_direction(
        instance: Any,
        requested_orders: Tuple[RequestedOrderIntent, ...],
        slot_id: int,
        symbol: str,
        current_position: float,
    ) -> int:
        """
        Backward-compatible wrapper returning only the mapped direction.
        """
        direction, _ = StrategyRunner._resolve_signal_mapping(
            instance=instance,
            requested_orders=requested_orders,
            slot_id=slot_id,
            symbol=symbol,
            current_position=current_position,
        )
        return direction

    @staticmethod
    def _select_primary_entry_order(
        requested_orders: Tuple[RequestedOrderIntent, ...],
        strategy_name: str,
        slot_id: int,
        symbol: str,
    ) -> Optional[RequestedOrderIntent]:
        """
        Returns the primary non-reduce-only order for bridge inference.
        """
        entry_orders = [
            order
            for order in requested_orders
            if not bool(order.reduce_only)
        ]
        if not entry_orders:
            return None
        if len(entry_orders) > 1:
            logger.warning(
                "StrategyRunner received multiple non-reduce-only orders on the "
                "same bar and will use the last one for provisional direction. "
                "strategy=%s slot_id=%s symbol=%s selected_order=%s "
                "entry_orders=%s",
                strategy_name,
                slot_id,
                symbol,
                StrategyRunner._format_requested_orders_for_log((entry_orders[-1],)),
                StrategyRunner._format_requested_orders_for_log(tuple(entry_orders)),
            )
        return entry_orders[-1]

    @staticmethod
    def _pending_entry_direction(
        requested_orders: Tuple[RequestedOrderIntent, ...],
        strategy_name: str,
        slot_id: int,
        symbol: str,
    ) -> int:
        """
        Infers direction from same-bar entry intents while flat.

        Reduce-only orders are intentionally excluded so protective exits do
        not request fresh exposure from the allocator.
        """
        primary_entry_order = StrategyRunner._select_primary_entry_order(
            requested_orders=requested_orders,
            strategy_name=strategy_name,
            slot_id=slot_id,
            symbol=symbol,
        )
        return StrategyRunner._direction_from_primary_entry_order(
            primary_entry_order=primary_entry_order,
            strategy_name=strategy_name,
            slot_id=slot_id,
            symbol=symbol,
            requested_orders=requested_orders,
        )

    @staticmethod
    def _direction_from_primary_entry_order(
        primary_entry_order: Optional[RequestedOrderIntent],
        strategy_name: str,
        slot_id: int,
        symbol: str,
        requested_orders: Tuple[RequestedOrderIntent, ...],
    ) -> int:
        """
        Converts one primary non-reduce-only order into a coarse direction.
        """
        if primary_entry_order is None:
            return 0
        return StrategyRunner._direction_from_order_side(
            side=primary_entry_order.side,
            strategy_name=strategy_name,
            slot_id=slot_id,
            symbol=symbol,
            requested_orders=requested_orders,
        )

    @staticmethod
    def _direction_from_order_side(
        side: Any,
        strategy_name: str,
        slot_id: int,
        symbol: str,
        requested_orders: Tuple[RequestedOrderIntent, ...],
    ) -> int:
        """
        Maps an order side into one coarse portfolio direction.
        """
        normalized_side = str(side).upper()
        if normalized_side == "BUY":
            return 1
        if normalized_side == "SELL":
            return -1
        logger.warning(
            "StrategyRunner could not infer pending-entry direction from raw "
            "order side and will emit direction=0. strategy=%s slot_id=%s "
            "symbol=%s selected_side=%r entry_orders=%s",
            strategy_name,
            slot_id,
            symbol,
            side,
            StrategyRunner._format_requested_orders_for_log(requested_orders),
        )
        return 0

    @staticmethod
    def _direction_from_signed_position(current_position: float) -> int:
        """
        Returns the coarse sign of the live position.
        """
        if current_position > 0:
            return 1
        if current_position < 0:
            return -1
        return 0

    @staticmethod
    def _legacy_state_requests_reversal(instance: Any, current_direction: int) -> bool:
        """
        Returns True when legacy runtime state has already flipped sides.
        """
        if not bool(getattr(instance, "_invested", False)):
            return False
        legacy_direction = StrategyRunner._direction_from_legacy_position_side(
            getattr(instance, "_position_side", None),
        )
        if current_direction > 0:
            return legacy_direction < 0
        if current_direction < 0:
            return legacy_direction > 0
        return False

    @staticmethod
    def _warn_on_flat_legacy_state_conflict(
        instance: Any,
        pending_direction: int,
        strategy_name: str,
        slot_id: int,
        symbol: str,
        current_position: float,
        requested_orders: Tuple[RequestedOrderIntent, ...],
    ) -> None:
        """
        Warns only when flat live state truly conflicts with legacy runtime flags.
        """
        pos_side = getattr(instance, "_position_side", None)
        legacy_direction = StrategyRunner._direction_from_legacy_position_side(pos_side)
        should_warn = pending_direction == 0 or legacy_direction != pending_direction
        if not should_warn:
            return
        logger.warning(
            "StrategyRunner encountered flat real position with conflicting legacy "
            "invested flags. strategy=%s slot_id=%s symbol=%s current_position=%s "
            "_invested=%s _position_side=%r pending_direction=%s requested_orders=%s",
            strategy_name,
            slot_id,
            symbol,
            current_position,
            bool(getattr(instance, "_invested", False)),
            pos_side,
            pending_direction,
            StrategyRunner._format_requested_orders_for_log(requested_orders),
        )

    @staticmethod
    def _direction_from_legacy_position_side(pos_side: Any) -> int:
        """
        Converts one legacy `_position_side` value into a coarse direction.
        """
        normalized_side = str(pos_side).upper()
        if normalized_side == "LONG":
            return 1
        if normalized_side == "SHORT":
            return -1
        return 0

    @staticmethod
    def _build_requested_orders(
        orders: List[Order],
    ) -> Tuple[RequestedOrderIntent, ...]:
        """
        Preserves the full raw order set emitted on a strategy bar.

        Methodology:
            Shared bracket inference is reused here so the portfolio bridge and
            the single-engine order book agree on which protective siblings are
            attached children and which order owns the primary execution intent.
        """
        metadata = infer_emitted_order_metadata(orders)
        requested_orders: List[RequestedOrderIntent] = []

        for order in orders:
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
                    oco_group_id=metadata.oco_group_ids.get(order.id),
                    oco_role=metadata.oco_roles.get(order.id),
                    parent_order_id=metadata.parent_order_ids.get(order.id),
                    activation_policy=metadata.activation_policies.get(order.id, "IMMEDIATE"),
                )
            )

        return tuple(requested_orders)

    @staticmethod
    def _select_primary_order(orders: List[Order]) -> Order:
        """Returns the primary bridge order inferred from one emitted batch."""
        metadata = infer_emitted_order_metadata(orders)
        primary_order_id = metadata.primary_order_id
        if primary_order_id is not None:
            for order in orders:
                if order.id == primary_order_id:
                    return order
        return orders[-1]

    @staticmethod
    def _format_requested_orders_for_log(
        requested_orders: Tuple[RequestedOrderIntent, ...],
    ) -> List[Dict[str, Any]]:
        """
        Returns a compact, JSON-like order summary for warning logs.

        Methodology:
            The runner emits structured diagnostics instead of repr-heavy object
            dumps so future debugging can compare raw order intent across
            strategies, allocation, and OMS layers without reopening Python
            objects interactively.
        """
        return [
            {
                "id": order.order_id,
                "side": order.side,
                "qty": order.quantity,
                "type": order.order_type,
                "reason": order.reason,
                "reduce_only": bool(order.reduce_only),
                "limit_price": order.limit_price,
                "stop_price": order.stop_price,
                "tif": order.time_in_force,
                "parent_order_id": order.parent_order_id,
                "activation_policy": order.activation_policy,
                "oco_role": order.oco_role,
            }
            for order in requested_orders
        ]
