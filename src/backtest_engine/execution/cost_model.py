"""
Shared execution cost helpers for the backtest engines.

This module centralizes order-type friction assumptions so the single-engine,
portfolio-engine, and optimization rough-cost paths can reuse the same logic
from one canonical place.
The default profile intentionally stays simple and retail-oriented:

- MARKET / STOP pay the configured spread model
- LIMIT / STOP_LIMIT do not pay default spread slippage
- all order types use the shared base commission_rate unless explicitly
  overridden via commission_rate_by_order_type

Future extensions can evolve this module without duplicating logic across
execution paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


SUPPORTED_ORDER_TYPES: tuple[str, ...] = ("MARKET", "LIMIT", "STOP", "STOP_LIMIT")
LIMIT_LIKE_ORDER_TYPES: tuple[str, ...] = ("LIMIT", "STOP_LIMIT")
MARKETABLE_ORDER_TYPES: tuple[str, ...] = ("MARKET", "STOP")

DEFAULT_SPREAD_TICK_MULTIPLIERS_BY_ORDER_TYPE: Mapping[str, float] = {
    **{order_type: 1.0 for order_type in MARKETABLE_ORDER_TYPES},
    **{order_type: 0.0 for order_type in LIMIT_LIKE_ORDER_TYPES},
}

DEFAULT_COMMISSION_RATE_MULTIPLIERS_BY_ORDER_TYPE: Mapping[str, float] = {
    "MARKET": 1.0,
    "LIMIT": 1.0,
    "STOP": 1.0,
    "STOP_LIMIT": 1.0,
}

__all__ = [
    "DEFAULT_COMMISSION_RATE_MULTIPLIERS_BY_ORDER_TYPE",
    "DEFAULT_SPREAD_TICK_MULTIPLIERS_BY_ORDER_TYPE",
    "ExecutionCostProfile",
    "LIMIT_LIKE_ORDER_TYPES",
    "MARKETABLE_ORDER_TYPES",
    "OrderCostEstimate",
    "RoundTripCostEstimate",
    "SUPPORTED_ORDER_TYPES",
    "estimate_order_cost",
    "estimate_round_trip_cost",
    "normalize_order_type",
    "resolve_execution_cost_profile",
    "resolve_spread_ticks",
]


@dataclass(frozen=True)
class ExecutionCostProfile:
    """
    Resolved per-order-type execution cost settings.

    Args:
        order_type: Normalized order type.
        spread_tick_multiplier: Spread multiplier applied to the shared spread
            model output for this order type.
        commission_rate: Per-contract commission for this order type.
    """

    order_type: str
    spread_tick_multiplier: float
    commission_rate: float


@dataclass(frozen=True)
class OrderCostEstimate:
    """
    Cash-cost estimate for one fill under the shared execution assumptions.

    Args:
        order_type: Normalized order type.
        quantity: Absolute contract quantity.
        spread_ticks: Effective spread ticks charged to this fill.
        slippage_price: Spread/slippage in price units per contract.
        slippage_cash: Spread/slippage translated into cash.
        commission_cash: Commission translated into cash.
        total_cash: Total execution friction in cash.
    """

    order_type: str
    quantity: float
    spread_ticks: int
    slippage_price: float
    slippage_cash: float
    commission_cash: float
    total_cash: float


@dataclass(frozen=True)
class RoundTripCostEstimate:
    """
    Cash-cost estimate for one round-trip trade.

    Args:
        entry: Entry-fill estimate.
        exit: Exit-fill estimate.
        total_cash: Sum of entry and exit execution costs.
    """

    entry: OrderCostEstimate
    exit: OrderCostEstimate
    total_cash: float


def normalize_order_type(order_type: str) -> str:
    """
    Returns a normalized order type validated against the execution contract.

    Args:
        order_type: Raw order type string.

    Returns:
        Uppercase normalized order type.

    Raises:
        ValueError: If the order type is not supported by the shared kernel.
    """

    normalized = str(order_type).upper()
    if normalized not in SUPPORTED_ORDER_TYPES:
        raise ValueError(
            f"Unsupported order type {order_type!r}. "
            f"Expected one of {SUPPORTED_ORDER_TYPES}."
        )
    return normalized


def resolve_execution_cost_profile(settings: Any, order_type: str) -> ExecutionCostProfile:
    """
    Resolves the shared execution cost profile for one order type.

    Methodology:
        1. Start from the repository-wide retail defaults.
        2. Apply exact order-type overrides from BacktestSettings when present.
        3. Fall back to the shared base commission_rate when no commission
           override is defined for the specific order type.

    Args:
        settings: Runtime settings object exposing execution cost attributes.
        order_type: Raw order type string.

    Returns:
        Resolved execution cost profile.
    """

    normalized = normalize_order_type(order_type)
    spread_overrides = _normalize_float_map(
        getattr(settings, "spread_tick_multipliers_by_order_type", {}) or {}
    )
    commission_overrides = _normalize_float_map(
        getattr(settings, "commission_rate_by_order_type", {}) or {}
    )

    if normalized in spread_overrides:
        spread_tick_multiplier = spread_overrides[normalized]
    else:
        spread_tick_multiplier = DEFAULT_SPREAD_TICK_MULTIPLIERS_BY_ORDER_TYPE[normalized]

    if normalized in commission_overrides:
        commission_rate = commission_overrides[normalized]
    else:
        base_rate = float(getattr(settings, "commission_rate", 0.0))
        commission_rate = (
            base_rate * DEFAULT_COMMISSION_RATE_MULTIPLIERS_BY_ORDER_TYPE[normalized]
        )

    return ExecutionCostProfile(
        order_type=normalized,
        spread_tick_multiplier=float(spread_tick_multiplier),
        commission_rate=float(commission_rate),
    )


def resolve_spread_ticks(
    settings: Any,
    order_type: str,
    effective_spread_ticks: Optional[int] = None,
) -> int:
    """
    Resolves the effective spread ticks charged to one fill.

    Args:
        settings: Runtime settings object exposing spread attributes.
        order_type: Raw order type string.
        effective_spread_ticks: Optional precomputed spread-model output from the
            engine. When omitted, settings.spread_ticks is used.

    Returns:
        Non-negative integer spread ticks for the requested order type.
    """

    profile = resolve_execution_cost_profile(settings, order_type)
    if effective_spread_ticks is None:
        base_ticks = int(getattr(settings, "spread_ticks", 0))
    else:
        base_ticks = int(effective_spread_ticks)
    return max(0, int(round(base_ticks * profile.spread_tick_multiplier)))


def estimate_order_cost(
    symbol: str,
    quantity: float,
    settings: Any,
    order_type: str = "MARKET",
    effective_spread_ticks: Optional[int] = None,
) -> OrderCostEstimate:
    """
    Estimates the cash execution cost of one fill.

    Args:
        symbol: Instrument symbol.
        quantity: Absolute or signed contract quantity.
        settings: Runtime settings object exposing instrument specs.
        order_type: Entry or exit order type.
        effective_spread_ticks: Optional spread-model output to reuse.

    Returns:
        Detailed order-cost estimate in both price units and cash.
    """

    profile = resolve_execution_cost_profile(settings, order_type)
    spread_ticks = resolve_spread_ticks(settings, order_type, effective_spread_ticks)
    quantity_abs = abs(float(quantity))
    spec = settings.get_instrument_spec(symbol)
    tick_size = float(spec["tick_size"])
    multiplier = float(spec["multiplier"])

    slippage_price = spread_ticks * tick_size
    slippage_cash = quantity_abs * slippage_price * multiplier
    commission_cash = quantity_abs * profile.commission_rate
    total_cash = slippage_cash + commission_cash

    return OrderCostEstimate(
        order_type=profile.order_type,
        quantity=quantity_abs,
        spread_ticks=spread_ticks,
        slippage_price=slippage_price,
        slippage_cash=slippage_cash,
        commission_cash=commission_cash,
        total_cash=total_cash,
    )


def estimate_round_trip_cost(
    symbol: str,
    settings: Any,
    quantity: float = 1.0,
    entry_order_type: str = "MARKET",
    exit_order_type: str = "MARKET",
    entry_effective_spread_ticks: Optional[int] = None,
    exit_effective_spread_ticks: Optional[int] = None,
) -> RoundTripCostEstimate:
    """
    Estimates the cash execution cost of one round-trip trade.

    Args:
        symbol: Instrument symbol.
        settings: Runtime settings object exposing instrument specs.
        quantity: Absolute or signed contract quantity per fill.
        entry_order_type: Entry order type.
        exit_order_type: Exit order type.
        entry_effective_spread_ticks: Optional entry spread-model output.
        exit_effective_spread_ticks: Optional exit spread-model output.

    Returns:
        Detailed round-trip execution-cost estimate.
    """

    entry = estimate_order_cost(
        symbol=symbol,
        quantity=quantity,
        settings=settings,
        order_type=entry_order_type,
        effective_spread_ticks=entry_effective_spread_ticks,
    )
    exit_ = estimate_order_cost(
        symbol=symbol,
        quantity=quantity,
        settings=settings,
        order_type=exit_order_type,
        effective_spread_ticks=exit_effective_spread_ticks,
    )
    return RoundTripCostEstimate(
        entry=entry,
        exit=exit_,
        total_cash=entry.total_cash + exit_.total_cash,
    )


def _normalize_float_map(raw_map: Mapping[Any, Any]) -> dict[str, float]:
    """
    Normalizes a user-provided override map to uppercase string keys.

    Args:
        raw_map: Mapping whose keys should represent order types.

    Returns:
        Uppercase-keyed float map.
    """

    normalized: dict[str, float] = {}
    for key, value in raw_map.items():
        normalized[str(key).upper()] = float(value)
    return normalized
