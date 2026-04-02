"""
Shared bracket-intent inference for legacy flat order lists.

Legacy strategies still return `List[Order]` without an explicit parent/child
structure. This helper extracts deterministic same-bar execution semantics so
both engines can agree on:

- which order is the primary order for bridge metadata
- which reduce-only siblings form one protective OCO bracket
- when protective siblings should stay dormant until a parent entry fills
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence
from uuid import uuid4


ACTIVATION_POLICY_IMMEDIATE = "IMMEDIATE"
ACTIVATION_POLICY_ON_PARENT_FILL = "ON_PARENT_FILL"


@dataclass(frozen=True)
class EmittedOrderMetadata:
    """Derived same-bar execution metadata for one emitted order batch."""

    primary_order_id: Optional[str]
    parent_order_ids: Dict[str, Optional[str]]
    activation_policies: Dict[str, str]
    oco_group_ids: Dict[str, Optional[str]]
    oco_roles: Dict[str, Optional[str]]


def infer_oco_role_from_order_type(order_type: str) -> str:
    """Maps one order type into a coarse OCO role."""
    if str(order_type).upper() in {"STOP", "STOP_LIMIT"}:
        return "STOP"
    return "TARGET"


def infer_emitted_order_metadata(orders: Sequence[object]) -> EmittedOrderMetadata:
    """
    Infers parent/child protective semantics from one legacy order batch.

    Methodology:
        1. The primary bridge order is the last non-reduce-only order when one
           exists, otherwise the last emitted order.
        2. Multiple same-bar reduce-only non-market siblings form one
           protective OCO candidate.
        3. Protective siblings are auto-attached to a parent only when the bar
           emitted exactly one non-reduce-only order and every protective child
           points to the opposite side.
    """
    emitted = list(orders)
    if not emitted:
        return EmittedOrderMetadata(
            primary_order_id=None,
            parent_order_ids={},
            activation_policies={},
            oco_group_ids={},
            oco_roles={},
        )

    entry_orders = [
        order
        for order in emitted
        if not bool(getattr(order, "reduce_only", False))
    ]
    protective_orders = [
        order
        for order in emitted
        if bool(getattr(order, "reduce_only", False))
        and str(getattr(order, "order_type", "")).upper() != "MARKET"
    ]

    primary_order = entry_orders[-1] if entry_orders else emitted[-1]

    parent_order_ids: Dict[str, Optional[str]] = {
        str(getattr(order, "id")): None for order in emitted
    }
    activation_policies: Dict[str, str] = {
        str(getattr(order, "id")): ACTIVATION_POLICY_IMMEDIATE for order in emitted
    }
    oco_group_ids: Dict[str, Optional[str]] = {
        str(getattr(order, "id")): None for order in emitted
    }
    oco_roles: Dict[str, Optional[str]] = {
        str(getattr(order, "id")): None for order in emitted
    }

    if len(protective_orders) >= 2:
        group_id = next(
            (
                str(getattr(order, "oco_group_id"))
                for order in protective_orders
                if getattr(order, "oco_group_id", None) is not None
            ),
            uuid4().hex,
        )
        for order in protective_orders:
            order_id = str(getattr(order, "id"))
            oco_group_ids[order_id] = str(getattr(order, "oco_group_id", None) or group_id)
            oco_roles[order_id] = str(
                getattr(order, "oco_role", None)
                or infer_oco_role_from_order_type(str(getattr(order, "order_type", "")))
            ).upper()

    attachable_parent = None
    if len(entry_orders) == 1 and protective_orders:
        candidate_parent = entry_orders[0]
        parent_side = str(getattr(candidate_parent, "side", "")).upper()
        all_opposing = all(
            str(getattr(order, "side", "")).upper() != parent_side
            for order in protective_orders
        )
        if all_opposing:
            attachable_parent = candidate_parent

    if attachable_parent is not None:
        parent_id = str(getattr(attachable_parent, "id"))
        for order in protective_orders:
            order_id = str(getattr(order, "id"))
            parent_order_ids[order_id] = parent_id
            activation_policies[order_id] = ACTIVATION_POLICY_ON_PARENT_FILL

    return EmittedOrderMetadata(
        primary_order_id=str(getattr(primary_order, "id")),
        parent_order_ids=parent_order_ids,
        activation_policies=activation_policies,
        oco_group_ids=oco_group_ids,
        oco_roles=oco_roles,
    )
