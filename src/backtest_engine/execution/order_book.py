"""
Single-engine resting order registry.

This module intentionally stays deterministic, but it now owns explicit
parent/child protective semantics for legacy same-bar entry+bracket batches.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Callable, List, Optional

from . import Fill, Order
from .brackets import (
    ACTIVATION_POLICY_IMMEDIATE,
    ACTIVATION_POLICY_ON_PARENT_FILL,
    infer_emitted_order_metadata,
    infer_oco_role_from_order_type,
)


_TERMINAL_STATUSES = {"CANCELLED", "REJECTED", "FILLED"}


class OrderBook:
    """
    Maintains active single-engine orders across bars.

    Methodology:
        Orders are submitted once, then carried bar-to-bar until they reach a
        terminal state. Parent entry fills can activate attached protective
        children on the same bar; cancelled parents cascade cancellation to
        their dormant children.
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
        self._assign_submission_metadata(orders)
        for order in orders:
            self.submit(order, placed_at)

    def cancel(self, order: Order) -> None:
        """
        Cancels an order and removes it from the active registry.
        """
        self.cancel_where(lambda active: active.id == order.id)

    def cancel_where(self, predicate: Callable[[Order], bool]) -> List[Order]:
        """
        Cancels every active order that matches the predicate.
        """
        cancelled_ids = {
            order.id for order in self._active_orders if predicate(order)
        }
        if not cancelled_ids:
            return []

        cancelled_ids = self._expand_descendant_ids(cancelled_ids)
        cancelled: List[Order] = []
        kept: List[Order] = []
        for order in self._active_orders:
            if order.id in cancelled_ids:
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
        preview_fill: Optional[Callable[[Order], Optional[float]]] = None,
        select_oco_winner: Optional[Callable[[List[Order]], Order]] = None,
    ) -> List[Fill]:
        """
        Attempts fills for all active orders and retains non-terminal residue.

        Methodology:
            Processing is iterative within one coarse bar so a parent fill can
            activate its attached protective children and those children can be
            evaluated on the same bar.
        """
        fills: List[Fill] = []
        remaining = list(self._active_orders)

        while True:
            progress_made = False
            next_remaining: List[Order] = []

            for group in self._group_orders(remaining):
                cleaned_group = [
                    order for order in group if order.status not in _TERMINAL_STATUSES
                ]
                if not cleaned_group:
                    continue

                ready, blocked = self._partition_ready_orders(
                    cleaned_group,
                    all_orders=remaining,
                    can_attempt=can_attempt,
                )
                if not ready:
                    next_remaining.extend(blocked)
                    continue

                group_fill = self._process_ready_group(
                    ready=ready,
                    blocked=blocked,
                    all_orders=remaining,
                    attempt_fill=attempt_fill,
                    preview_fill=preview_fill,
                    select_oco_winner=select_oco_winner,
                )
                if group_fill:
                    fills.extend(group_fill)
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

    @staticmethod
    def _assign_submission_metadata(orders: List[Order]) -> None:
        """
        Applies shared same-bar bracket metadata to a submitted order batch.
        """
        metadata = infer_emitted_order_metadata(orders)
        for order in orders:
            order_id = order.id
            inferred_group_id = metadata.oco_group_ids.get(order_id)
            inferred_role = metadata.oco_roles.get(order_id)
            parent_order_id = metadata.parent_order_ids.get(order_id)
            activation_policy = metadata.activation_policies.get(
                order_id,
                ACTIVATION_POLICY_IMMEDIATE,
            )

            if inferred_group_id is not None and order.oco_group_id is None:
                order.oco_group_id = inferred_group_id
            if inferred_role is not None and order.oco_role is None:
                order.oco_role = inferred_role
            if order.oco_role is None and bool(order.reduce_only):
                order.oco_role = infer_oco_role_from_order_type(str(order.order_type))

            if parent_order_id is not None and order.parent_order_id is None:
                order.parent_order_id = parent_order_id
            order.activation_policy = activation_policy
            if (
                order.parent_order_id is not None
                and order.activation_policy == ACTIVATION_POLICY_ON_PARENT_FILL
            ):
                order.activation_status = "PENDING_PARENT_FILL"
            else:
                order.activation_status = "ACTIVE"

    def _partition_ready_orders(
        self,
        group: List[Order],
        all_orders: List[Order],
        can_attempt: Callable[[Order], bool],
    ) -> tuple[List[Order], List[Order]]:
        """
        Splits one order group into executable and blocked members.
        """
        ready: List[Order] = []
        blocked: List[Order] = []
        for order in group:
            if not self._is_ready_for_execution(order, all_orders):
                if order.status not in _TERMINAL_STATUSES:
                    blocked.append(order)
                continue
            if can_attempt(order):
                ready.append(order)
            else:
                blocked.append(order)
        return ready, blocked

    def _process_ready_group(
        self,
        ready: List[Order],
        blocked: List[Order],
        all_orders: List[Order],
        attempt_fill: Callable[[Order], Optional[Fill]],
        preview_fill: Optional[Callable[[Order], Optional[float]]],
        select_oco_winner: Optional[Callable[[List[Order]], Order]],
    ) -> List[Fill]:
        """
        Processes one executable group and handles parent/child transitions.
        """
        if len(ready) == 1 or ready[0].oco_group_id is None or preview_fill is None:
            fills: List[Fill] = []
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

    def _is_ready_for_execution(self, order: Order, all_orders: List[Order]) -> bool:
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
        parent: Order,
        all_orders: List[Order],
        fill: Fill,
    ) -> None:
        """
        Arms dormant child orders once their parent entry fills.
        """
        for order in all_orders:
            if order.parent_order_id != parent.id:
                continue
            if order.status in _TERMINAL_STATUSES:
                continue
            order.quantity = float(abs(fill.order.quantity))
            order.activation_status = "ACTIVE"
            order.activated_at = fill.timestamp
            order.activated_by_fill_phase = str(fill.fill_phase).upper()

    @staticmethod
    def _cancel_children_for_parent(parent: Order, all_orders: List[Order]) -> None:
        """
        Cancels every dormant or active child belonging to one terminal parent.
        """
        for order in all_orders:
            if order.parent_order_id == parent.id and order.status not in _TERMINAL_STATUSES:
                order.status = "CANCELLED"

    def _group_orders(self, orders: List[Order]) -> List[List[Order]]:
        """
        Returns orders grouped by OCO identifier while preserving insertion order.
        """
        grouped: List[List[Order]] = []
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
    def _select_oco_winner(orders: List[Order]) -> Order:
        """
        Picks the deterministic fill winner inside an OCO group.

        Methodology:
            On a coarse OHLC bar we cannot observe the true intrabar path. The
            single-engine fallback is therefore pessimistic: if both stop and
            target are reachable on the same bar, the stop wins.
        """
        stops = [
            order
            for order in orders
            if str(order.oco_role or infer_oco_role_from_order_type(str(order.order_type))).upper() == "STOP"
        ]
        if stops:
            return sorted(stops, key=lambda order: order.id)[0]
        return sorted(orders, key=lambda order: order.id)[0]

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
