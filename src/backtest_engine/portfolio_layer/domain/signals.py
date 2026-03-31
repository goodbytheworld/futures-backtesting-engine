"""
src/backtest_engine/portfolio_layer/domain/signals.py

Directional signal and target-position contracts.

Responsibility: Pure data carriers between StrategyRunner → Allocator → Engine.
No computation here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class RequestedOrderIntent:
    """
    Raw strategy order metadata preserved for incremental portfolio OMS wiring.

    Methodology:
        The portfolio path still remains target-driven, but phase 9 needs the
        full set of raw non-market intents from a single strategy bar so the
        engine can support explicit replace semantics and OCO-like protective
        stop/target coordination without promoting the whole engine to a fully
        order-driven architecture.
    """

    order_id: str
    side: str
    quantity: float
    order_type: str
    reason: str = "SIGNAL"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "GTC"
    reduce_only: bool = False
    oco_group_id: Optional[str] = None
    oco_role: Optional[str] = None


@dataclass
class StrategySignal:
    """
    Directional intent emitted by a StrategyRunner for a specific (slot, symbol).

    The portfolio engine converts signals into target positions; sizing happens
    in the Allocator — not inside the strategy.

    During the incremental portfolio-OMS migration this object also carries the
    raw execution intent emitted by the underlying legacy strategy order. The
    allocator currently ignores those optional fields; they exist so the
    portfolio path stops discarding limit/stop/reduce-only metadata at the
    strategy-to-engine boundary.

    Attributes:
        slot_id: Index of the originating StrategySlot in PortfolioConfig.slots.
        symbol: Ticker this signal targets.
        direction: +1 (long), -1 (short), 0 (flat / exit).
        reason: Human-readable tag (e.g. 'SIGNAL', 'SL', 'TP', 'EXIT').
        timestamp: Bar timestamp at which the signal was generated (close[t]).
        requested_order_id: Raw strategy order identifier for tracing/debugging.
        requested_side: Raw order side ('BUY' / 'SELL') from the legacy strategy.
        requested_quantity: Raw order quantity from the legacy strategy.
            Preserved for traceability/bridge purposes only; it is not
            authoritative for portfolio sizing or child-order quantity in the
            current OMS iteration.
        requested_order_type: Raw order type ('MARKET', 'LIMIT', 'STOP', ...).
        requested_limit_price: Requested limit price, if any.
        requested_stop_price: Requested stop price, if any.
        requested_time_in_force: Requested time-in-force ('DAY', 'GTC', 'IOC').
        requested_reduce_only: Raw reduce-only flag from the strategy order.
        requested_orders: Full raw order set emitted on this bar. The legacy
            single-order fields above are preserved for compatibility and still
            point to the last emitted order.
    """
    slot_id: int
    symbol: str
    direction: int              # +1 / -1 / 0
    reason: str = "SIGNAL"
    timestamp: Optional[object] = None
    requested_order_id: Optional[str] = None
    requested_side: Optional[str] = None
    # Preserved for traceability/bridge purposes only. It is not authoritative
    # for portfolio sizing or child-order quantity in the current OMS iteration.
    requested_quantity: Optional[float] = None
    requested_order_type: Optional[str] = None
    requested_limit_price: Optional[float] = None
    requested_stop_price: Optional[float] = None
    requested_time_in_force: Optional[str] = None
    requested_reduce_only: bool = False
    requested_orders: Tuple[RequestedOrderIntent, ...] = field(default_factory=tuple)


@dataclass
class TargetPosition:
    """
    Desired signed contract quantity for a (slot_id, symbol) pair.

    Produced by the Allocator and consumed by the portfolio engine to
    compute order deltas.

    Attributes:
        slot_id: Originating strategy slot.
        symbol: Ticker.
        target_qty: Signed contracts (positive = long, negative = short).
    """
    slot_id: int
    symbol: str
    target_qty: float
    reason: str = "PORTFOLIO_SYNC"
