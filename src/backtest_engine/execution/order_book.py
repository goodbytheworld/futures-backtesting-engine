"""
Single-engine resting order registry.

This module intentionally stays small and deterministic. It is not a full OMS
for the entire repository yet; it provides the single-asset engine with an
explicit place to own order state transitions and active resting orders.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Callable, List, Optional

from . import Fill, Order


class OrderBook:
    """
    Maintains active single-engine orders across bars.

    Methodology:
        Orders are submitted once, then carried bar-to-bar until they reach a
        terminal state. The engine remains responsible for session policy and
        liquidation priority; the book owns storage and state transitions.
    """

    def __init__(self) -> None:
        self._active_orders: List[Order] = []

    def has_open_orders(self) -> bool:
        """Returns True when any active order remains in the registry."""
        return bool(self._active_orders)

    def active_orders(self) -> List[Order]:
        """Returns a shallow copy of the active order list."""
        return list(self._active_orders)

    def submit(self, order: Order, placed_at) -> None:
        """
        Submits a single order into the active registry.
        """
        if order.timestamp is None:
            order.timestamp = placed_at
        if order.placed_at is None:
            order.placed_at = placed_at
        if order.status == "NEW":
            order.status = "SUBMITTED"
        self._active_orders.append(order)

    def submit_many(self, orders: List[Order], placed_at) -> None:
        """
        Submits multiple orders at the same engine timestamp.
        """
        for order in orders:
            self.submit(order, placed_at)

    def cancel(self, order: Order) -> None:
        """
        Cancels an order and removes it from the active registry.
        """
        order.status = "CANCELLED"
        self._active_orders = [active for active in self._active_orders if active.id != order.id]

    def cancel_where(self, predicate: Callable[[Order], bool]) -> List[Order]:
        """
        Cancels every active order that matches the predicate.
        """
        cancelled: List[Order] = []
        kept: List[Order] = []
        for order in self._active_orders:
            if predicate(order):
                order.status = "CANCELLED"
                cancelled.append(order)
            else:
                kept.append(order)
        self._active_orders = kept
        return cancelled

    def pull_where(self, predicate: Callable[[Order], bool]) -> List[Order]:
        """
        Removes matching active orders without changing their status.
        """
        pulled: List[Order] = []
        kept: List[Order] = []
        for order in self._active_orders:
            if predicate(order):
                pulled.append(order)
            else:
                kept.append(order)
        self._active_orders = kept
        return pulled

    def cancel_expired_day_orders(self, current_date: date) -> List[Order]:
        """
        Cancels DAY orders once the engine crosses into a later calendar date.
        """
        return self.cancel_where(
            lambda order: (
                str(order.time_in_force).upper() == "DAY"
                and order.placed_at is not None
                and self._placement_date(order) < current_date
            )
        )

    def process_active_orders(
        self,
        attempt_fill: Callable[[Order], Optional[Fill]],
        can_attempt: Callable[[Order], bool],
    ) -> List[Fill]:
        """
        Attempts fills for all active orders and retains non-terminal residue.
        """
        retained: List[Order] = []
        fills: List[Fill] = []

        for order in self._active_orders:
            if not can_attempt(order):
                retained.append(order)
                continue

            fill = attempt_fill(order)
            if fill is not None:
                fills.append(fill)
                continue

            if order.status not in {"CANCELLED", "REJECTED", "FILLED"}:
                retained.append(order)

        self._active_orders = retained
        return fills

    @staticmethod
    def _placement_date(order: Order) -> date:
        """
        Normalizes placement timestamps into calendar dates.
        """
        if isinstance(order.placed_at, datetime):
            return order.placed_at.date()
        if isinstance(order.placed_at, date):
            return order.placed_at
        raise TypeError("Order.placed_at must be date-like when expiring DAY orders.")
