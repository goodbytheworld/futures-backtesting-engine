"""
Resting order registry for the portfolio engine.

The portfolio path now owns explicit parent/child protective semantics for
same-bar entry+bracket batches instead of treating them as loose siblings.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Callable, List, Optional

from ..domain.orders import PendingPortfolioOrder


_TERMINAL_STATUSES = {"CANCELLED", "REJECTED", "FILLED"}


class PortfolioOrderBook:
    """
    Stores active pending portfolio orders across bars.

    Methodology:
        Orders remain active until they are filled, cancelled, or explicitly
        replaced. Parent entry fills can activate attached protective children
        on the same coarse bar; cancelled parents cascade cancellation to all
        descendants.
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
        if order.parent_order_id is not None and not order.is_ready_for_execution:
            order.activation_status = "PENDING_PARENT_FILL"
        else:
            order.activation_status = "ACTIVE"
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
        cancelled_ids = {
            order.id
            for order in self._active_orders
            if predicate(order)
        }
        if not cancelled_ids:
            return []

        cancelled_ids = self._expand_descendant_ids(cancelled_ids)
        cancelled: List[PendingPortfolioOrder] = []
        kept: List[PendingPortfolioOrder] = []
        for order in self._active_orders:
            if order.id in cancelled_ids:
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

    def process_active_orders(
        self,
        attempt_fill: Callable[[PendingPortfolioOrder], Optional[object]],
        can_attempt: Callable[[PendingPortfolioOrder], bool],
        preview_fill: Optional[Callable[[PendingPortfolioOrder], Optional[float]]] = None,
        select_oco_winner: Optional[Callable[[List[PendingPortfolioOrder]], PendingPortfolioOrder]] = None,
    ) -> List[object]:
        """
        Attempts fills for all active orders and retains non-terminal residue.

        Methodology:
            Processing is iterative within one coarse bar so a filled parent can
            activate attached protective children immediately and those children
            can then be evaluated on the same bar.
        """
        fills: List[object] = []
        remaining = list(self._active_orders)

        while True:
            progress_made = False
            next_remaining: List[PendingPortfolioOrder] = []

            for group in self._group_orders(remaining):
                cleaned_group = [
                    order
                    for order in group
                    if order.status not in _TERMINAL_STATUSES
                ]
                if not cleaned_group:
                    continue

                ready, blocked = self._partition_ready_orders(
                    cleaned_group,
                    all_orders=remaining,
                    can_attempt=can_attempt,
                )
                if not ready:
                    next_remaining.extend(
                        order
                        for order in blocked
                        if order.status not in _TERMINAL_STATUSES
                    )
                    continue

                group_fills = self._process_ready_group(
                    ready=ready,
                    blocked=blocked,
                    all_orders=remaining,
                    attempt_fill=attempt_fill,
                    preview_fill=preview_fill,
                    select_oco_winner=select_oco_winner,
                )
                if group_fills:
                    fills.extend(group_fills)
                    progress_made = True

                next_remaining.extend(
                    order
                    for order in blocked + ready
                    if order.status not in _TERMINAL_STATUSES
                )

            remaining = [
                order
                for order in next_remaining
                if order.status not in _TERMINAL_STATUSES
            ]
            if not progress_made:
                self._active_orders = remaining
                return fills

    def _partition_ready_orders(
        self,
        group: List[PendingPortfolioOrder],
        all_orders: List[PendingPortfolioOrder],
        can_attempt: Callable[[PendingPortfolioOrder], bool],
    ) -> tuple[List[PendingPortfolioOrder], List[PendingPortfolioOrder]]:
        """
        Splits one order group into executable and blocked members.
        """
        ready: List[PendingPortfolioOrder] = []
        blocked: List[PendingPortfolioOrder] = []
        for order in group:
            if not self._is_ready_for_execution(order, all_orders):
                if order.status not in _TERMINAL_STATUSES:
                    blocked.append(order)
                continue
            if can_attempt(order):
                ready.append(order)
            elif order.status not in _TERMINAL_STATUSES:
                blocked.append(order)
        return ready, blocked

    def _process_ready_group(
        self,
        ready: List[PendingPortfolioOrder],
        blocked: List[PendingPortfolioOrder],
        all_orders: List[PendingPortfolioOrder],
        attempt_fill: Callable[[PendingPortfolioOrder], Optional[object]],
        preview_fill: Optional[Callable[[PendingPortfolioOrder], Optional[float]]],
        select_oco_winner: Optional[
            Callable[[List[PendingPortfolioOrder]], PendingPortfolioOrder]
        ],
    ) -> List[object]:
        """
        Processes one executable group and handles parent/child transitions.
        """
        if len(ready) == 1 or ready[0].oco_group_id is None or preview_fill is None:
            fills: List[object] = []
            for order in ready:
                fill = attempt_fill(order)
                if fill is not None:
                    fills.append(fill)
                    self._activate_children_for_parent(
                        parent=order,
                        all_orders=all_orders,
                        fill=fill,
                    )
                    continue
                if order.status in {"CANCELLED", "REJECTED"}:
                    self._cancel_children_for_parent(order, all_orders)
            return fills

        fillable = [order for order in ready if preview_fill(order) is not None]
        if not fillable:
            return []

        winner = (
            select_oco_winner(fillable)
            if select_oco_winner is not None
            else self._select_oco_winner(fillable)
        )
        fill = attempt_fill(winner)
        if fill is None:
            if winner.status in {"CANCELLED", "REJECTED"}:
                self._cancel_children_for_parent(winner, all_orders)
            return []

        self._activate_children_for_parent(
            parent=winner,
            all_orders=all_orders,
            fill=fill,
        )
        for sibling in ready + blocked:
            if sibling.id == winner.id:
                continue
            sibling.status = "CANCELLED"
            self._cancel_children_for_parent(sibling, all_orders)
        return [fill]

    def _is_ready_for_execution(
        self,
        order: PendingPortfolioOrder,
        all_orders: List[PendingPortfolioOrder],
    ) -> bool:
        """
        Returns True when an order can be attempted on the current bar.
        """
        if order.status in _TERMINAL_STATUSES:
            return False
        if str(order.activation_status).upper() != "PENDING_PARENT_FILL":
            return True

        parent_id = order.parent_order_id
        if parent_id is None:
            order.activation_status = "ACTIVE"
            return True

        parent = next(
            (active for active in all_orders if active.id == parent_id),
            None,
        )
        if parent is None:
            order.status = "CANCELLED"
            return False
        if parent.status in {"CANCELLED", "REJECTED"}:
            order.status = "CANCELLED"
            return False
        return False

    @staticmethod
    def _activate_children_for_parent(
        parent: PendingPortfolioOrder,
        all_orders: List[PendingPortfolioOrder],
        fill: object,
    ) -> None:
        """
        Arms dormant child orders once their parent entry fills.
        """
        fill_order = getattr(fill, "order", None)
        filled_quantity = float(abs(getattr(fill_order, "quantity", parent.quantity)))
        fill_timestamp = getattr(fill, "timestamp", None)
        fill_phase = str(getattr(fill, "fill_phase", "OPEN")).upper()
        for order in all_orders:
            if order.parent_order_id != parent.id:
                continue
            if order.status in _TERMINAL_STATUSES:
                continue
            order.quantity = filled_quantity
            order.activation_status = "ACTIVE"
            order.activated_at = fill_timestamp
            order.activated_by_fill_phase = fill_phase

    @staticmethod
    def _cancel_children_for_parent(
        parent: PendingPortfolioOrder,
        all_orders: List[PendingPortfolioOrder],
    ) -> None:
        """
        Cancels every dormant or active child belonging to one terminal parent.
        """
        for order in all_orders:
            if order.parent_order_id == parent.id and order.status not in _TERMINAL_STATUSES:
                order.status = "CANCELLED"

    def _group_orders(
        self,
        orders: List[PendingPortfolioOrder],
    ) -> List[List[PendingPortfolioOrder]]:
        """
        Returns orders grouped by OCO identifier while preserving insertion order.
        """
        grouped: List[List[PendingPortfolioOrder]] = []
        seen: set[str] = set()
        for order in orders:
            group_id = order.oco_group_id or order.id
            if group_id in seen:
                continue
            seen.add(group_id)
            grouped.append(
                [
                    active
                    for active in orders
                    if (active.oco_group_id or active.id) == group_id
                ]
            )
        return grouped

    def _expand_descendant_ids(self, root_ids: set[str]) -> set[str]:
        """
        Expands a root order-id set to include every active child descendant.
        """
        expanded = set(root_ids)
        changed = True
        while changed:
            changed = False
            for order in self._active_orders:
                if order.parent_order_id in expanded and order.id not in expanded:
                    expanded.add(order.id)
                    changed = True
        return expanded

    @staticmethod
    def _select_oco_winner(
        orders: List[PendingPortfolioOrder],
    ) -> PendingPortfolioOrder:
        """
        Picks the deterministic fill winner inside an OCO group.

        Methodology:
            On a coarse OHLC bar we cannot observe the true intrabar path. The
            fallback remains pessimistic: if both stop and target are reachable
            on the same bar, the stop wins.
        """
        stops = [
            order
            for order in orders
            if str(order.oco_role or "").upper() == "STOP"
            or str(order.order_type).upper() in {"STOP", "STOP_LIMIT"}
        ]
        if stops:
            return sorted(stops, key=lambda order: order.id)[0]
        return sorted(orders, key=lambda order: order.id)[0]

    @staticmethod
    def _placement_date(order: PendingPortfolioOrder) -> date:
        """
        Normalizes placement timestamps into calendar dates.
        """
        if isinstance(order.placed_at, datetime):
            return order.placed_at.date()
        if isinstance(order.placed_at, date):
            return order.placed_at
        raise TypeError("PendingPortfolioOrder.placed_at must be date-like.")
