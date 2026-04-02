"""
Portfolio-engine execution carriers.

Responsibility: lightweight typed objects used inside the portfolio engine's
event loop before a dedicated portfolio OMS exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4

from src.backtest_engine.execution.brackets import ACTIVATION_POLICY_IMMEDIATE


@dataclass
class PendingPortfolioOrder:
    """
    Resting portfolio-engine order delta awaiting execution.

    Methodology:
        This object is intentionally smaller than the shared single-engine
        `Order`. The current portfolio path still computes deltas from allocator
        targets and executes them as market orders on the next eligible bar.
        The dataclass replaces the previous tuple contract so carry-forward and
        netting semantics are explicit.
    """

    slot_id: int
    symbol: str
    side: str
    quantity: float
    id: str = field(default_factory=lambda: uuid4().hex)
    reason: str = "PORTFOLIO_SYNC"
    order_type: str = "MARKET"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "GTC"
    reduce_only: bool = False
    source: str = "TARGET_SYNC"
    requested_order_id: Optional[str] = None
    oco_group_id: Optional[str] = None
    oco_role: Optional[str] = None
    parent_order_id: Optional[str] = None
    activation_policy: str = ACTIVATION_POLICY_IMMEDIATE
    activation_status: str = "ACTIVE"
    activated_at: Optional[object] = None
    activated_by_fill_phase: Optional[str] = None
    placed_at: Optional[object] = None
    eligible_from: Optional[object] = None
    status: str = "NEW"

    @property
    def signed_quantity(self) -> float:
        """Returns the signed quantity implied by side and absolute quantity."""
        return self.quantity if self.side == "BUY" else -self.quantity

    @property
    def is_priority(self) -> bool:
        """Returns True when the order should bypass normal session gating."""
        return "RISK" in self.reason or self.reason == "EOD_CLOSE"

    @property
    def owns_resting_execution_state(self) -> bool:
        """
        Returns True when the order should block new normal deltas for its key.

        Methodology:
            During the incremental portfolio-OMS migration, a live non-market
            signal-templated order is treated as the active execution state for
            its (slot_id, symbol). The allocator may still update target state,
            but the engine must not queue overlapping normal deltas until this
            resting order resolves or is explicitly replaced in a later phase.
        """
        return self.source == "SIGNAL_TEMPLATE" and str(self.order_type).upper() != "MARKET"

    @property
    def is_ready_for_execution(self) -> bool:
        """Returns True when the order is armed for actual execution attempts."""
        return str(self.activation_status).upper() != "PENDING_PARENT_FILL"
