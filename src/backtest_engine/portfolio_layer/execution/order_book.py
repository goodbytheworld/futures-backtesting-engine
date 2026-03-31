"""
Resting order registry for the portfolio engine.

This module still does not implement a full portfolio OMS. It stores typed
pending orders so execution state is separated from allocator target state while
the event-loop model remains target-driven.
"""

from __future__ import annotations

from typing import Callable, List

from ..domain.orders import PendingPortfolioOrder


class PortfolioOrderBook:
    """
    Stores active pending portfolio orders across bars.

    Methodology:
        Orders are submitted after target-delta computation and remain active
        until they are filled, cancelled, or replaced by explicit engine logic.
        This book stores typed pending orders, but it is still not a full
        stop/limit OMS with dedicated cancel/replace and child-order semantics.
    """

    def __init__(self) -> None:
        self._active_orders: List[PendingPortfolioOrder] = []

    def has_open_orders(self) -> bool:
        """Returns True when any pending portfolio order remains active."""
        return bool(self._active_orders)

    def active_orders(self) -> List[PendingPortfolioOrder]:
        """Returns a shallow copy of active orders."""
        return list(self._active_orders)

    def submit(
        self,
        order: PendingPortfolioOrder,
        placed_at,
        eligible_from=None,
    ) -> None:
        """
        Submits a portfolio order into the active registry.
        """
        if order.placed_at is None:
            order.placed_at = placed_at
        if order.eligible_from is None:
            order.eligible_from = eligible_from
        if order.status == "NEW":
            order.status = "SUBMITTED"
        self._active_orders.append(order)

    def submit_many(
        self,
        orders: List[PendingPortfolioOrder],
        placed_at,
        eligible_from=None,
    ) -> None:
        """
        Submits multiple portfolio orders with common placement metadata.
        """
        for order in orders:
            self.submit(order, placed_at=placed_at, eligible_from=eligible_from)

    def replace_active_orders(self, orders: List[PendingPortfolioOrder]) -> None:
        """
        Replaces the current active-order set with the provided list.
        """
        self._active_orders = list(orders)

    def cancel_where(
        self,
        predicate: Callable[[PendingPortfolioOrder], bool],
    ) -> List[PendingPortfolioOrder]:
        """
        Cancels matching active orders and removes them from the book.
        """
        cancelled: List[PendingPortfolioOrder] = []
        kept: List[PendingPortfolioOrder] = []
        for order in self._active_orders:
            if predicate(order):
                order.status = "CANCELLED"
                cancelled.append(order)
            else:
                kept.append(order)
        self._active_orders = kept
        return cancelled

    def pull_all(self) -> List[PendingPortfolioOrder]:
        """
        Removes and returns all active orders without mutating their status.
        """
        pulled = list(self._active_orders)
        self._active_orders = []
        return pulled
