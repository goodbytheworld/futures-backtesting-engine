from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pandas as pd

from .brackets import ACTIVATION_POLICY_IMMEDIATE
from .cost_model import (
    estimate_order_cost,
    estimate_round_trip_cost,
    resolve_execution_cost_profile,
    resolve_spread_ticks,
)

@dataclass
class Order:
    """
    Represents an intent to trade at a specific time.
    """
    symbol: str
    quantity: float
    side: str # 'BUY' or 'SELL'
    order_type: str = 'MARKET'
    reason: str = 'SIGNAL' # e.g., 'SIGNAL', 'SL', 'TP', 'TIME'
    timestamp: Optional[datetime] = None
    id: str = field(default_factory=lambda: uuid4().hex)
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "DAY"
    placed_at: Optional[datetime] = None
    status: str = "NEW"
    reduce_only: bool = False
    oco_group_id: Optional[str] = None
    oco_role: Optional[str] = None
    parent_order_id: Optional[str] = None
    activation_policy: str = ACTIVATION_POLICY_IMMEDIATE
    activation_status: str = "ACTIVE"
    activated_at: Optional[object] = None
    activated_by_fill_phase: Optional[str] = None

@dataclass
class Fill:
    """
    Represents a finalized trade execution against the market.

    Methodology:
    `slippage` is stored in price units per contract so the fill record preserves
    the actual execution-price adjustment applied by the simulator.
    """
    order: Order
    fill_price: float
    commission: float
    slippage: float
    cost: float
    timestamp: datetime
    fill_phase: str = "OPEN"

    @property
    def order_id(self) -> str:
        """Compatibility accessor for execution-report style consumers."""
        return self.order.id
    
@dataclass
class Trade:
    """
    Represents a completed round-trip trade (Entry + Exit) for analytics scoring.

    Methodology:
    `pnl` is net realized PnL after commissions using the actual executed entry
    and exit prices. Because those executed prices already embed slippage,
    `slippage` stays as a separate positive dollar-cost field for decomposition
    and signal-vs-execution analytics rather than being subtracted again.
    `commission` and `slippage` are stored as positive dollar cost magnitudes for
    the completed round trip so exporters and dashboard analytics do not need to
    infer units from the execution layer.
    """
    symbol: str
    entry_price: float
    exit_price: float
    quantity: float
    direction: str # 'LONG' or 'SHORT'
    entry_time: datetime
    exit_time: datetime
    pnl: float
    commission: float
    slippage: float = 0.0
    exit_reason: str = 'SIGNAL'
    entry_signal_time: Optional[datetime] = None

class ExecutionHandler:
    """
    Handles order execution tracking and simulates fills into Round-trip Trades.

    Methodology:
    Fill prices are adjusted by the shared execution cost model. The number of
    spread ticks applied per fill is supplied by the calling engine via the
    `effective_spread_ticks` parameter, which is computed from
    `spread_model.compute_spread_ticks()` before each execution.  The shared
    cost model then applies the order-type profile:

    - MARKET / STOP use the spread model by default
    - LIMIT / STOP_LIMIT default to zero spread slippage unless explicitly overridden

    When `effective_spread_ticks` is not provided the handler reads
    `settings.spread_ticks` directly (appropriate for static mode and tests).
    No random number generator is used anywhere in this class.
    """
    
    def __init__(self, settings: Any):
        """
        Initializes the ExecutionHandler.
        
        Args:
            settings: Configuration object containing trading specifications and fee models.
        """
        self.settings = settings
        self.fills: List[Fill] = []
        self.trades: List[Trade] = []
        
        # Position tracking for Trade matching (FIFO basis)
        self._positions: Dict[str, List[Fill]] = {} 

    def execute_order(
        self,
        order: Order,
        data_bar: pd.Series,
        execute_at_close: bool = False,
        effective_spread_ticks: Optional[int] = None,
        current_position: float = 0.0,
    ) -> Optional[Fill]:
        """
        Simulates order execution with deterministic spread and commission constraints.
        
        Methodology:
        Derives an execution price adjusted by the shared execution cost model.
        The spread tick count is either supplied externally by the engine
        (adaptive mode) or read from settings.spread_ticks (static mode). The
        order-type profile then decides whether that spread applies to the
        fill. No random sampling is performed; the same inputs always produce
        the same output.

        Fill-price convention:
            BUY  fill: price + spread_ticks * tick_size
            SELL fill: price - spread_ticks * tick_size
        
        Args:
            order: The Order object to execute.
            data_bar: The current OHLCV bar representing the market state at execution.
            execute_at_close: Evaluates execution against close prices if True,
                              open prices otherwise.
            effective_spread_ticks: Pre-computed tick count from the spread model.
                                    If None, falls back to settings.spread_ticks.
            
        Returns:
            The executed Fill object, or None if execution fails.
        """
        spec = self.settings.get_instrument_spec(order.symbol)
        order_type = str(order.order_type).upper()

        if not self._validate_order(order, order_type):
            return None

        executable_quantity = self._resolve_executable_quantity(
            order=order,
            current_position=current_position,
        )
        if executable_quantity <= 0:
            order.status = "CANCELLED" if bool(order.reduce_only) else "REJECTED"
            return None
        order.quantity = float(executable_quantity)

        self._accept_order(order)
        fill_price, fill_phase = self._resolve_bar_fill_details(
            order=order,
            order_type=order_type,
            data_bar=data_bar,
            execute_at_close=execute_at_close,
        )
        if fill_price is None:
            if str(order.time_in_force).upper() == "IOC":
                order.status = "CANCELLED"
            return None

        ticks = self._resolve_spread_ticks(order_type, effective_spread_ticks)
        slippage = ticks * spec["tick_size"]
        executed_price = fill_price + slippage if order.side == 'BUY' else fill_price - slippage
        commission = abs(order.quantity) * self._resolve_commission_rate(order_type)
        cost = (executed_price * order.quantity) if order.side == 'BUY' else -(executed_price * order.quantity)
        order.status = "FILLED"

        fill = Fill(
            order=order,
            fill_price=executed_price,
            commission=commission,
            slippage=slippage,
            cost=cost,
            timestamp=data_bar.name if isinstance(data_bar.name, datetime) else order.timestamp,
            fill_phase=fill_phase,
        )
        self.fills.append(fill)
        self._process_trades(fill)
        return fill

    def _validate_order(self, order: Order, order_type: str) -> bool:
        """
        Validates the minimum price fields required for each order type.
        """
        if order.quantity <= 0:
            order.status = "REJECTED"
            return False

        if order_type == "LIMIT" and order.limit_price is None:
            order.status = "REJECTED"
            return False
        if order_type == "STOP" and order.stop_price is None:
            order.status = "REJECTED"
            return False
        if order_type == "STOP_LIMIT":
            if order.stop_price is None or order.limit_price is None:
                order.status = "REJECTED"
                return False

        if order_type not in {"MARKET", "LIMIT", "STOP", "STOP_LIMIT"}:
            order.status = "REJECTED"
            return False
        return True

    def _accept_order(self, order: Order) -> None:
        """
        Transitions a new order into the accepted state.
        """
        if order.status in {"NEW", "SUBMITTED"}:
            order.status = "ACCEPTED"

    @staticmethod
    def _resolve_executable_quantity(order: Order, current_position: float) -> float:
        """
        Applies reduce-only quantity caps against the live opposing position.

        Methodology:
            The shared execution kernel still does not own the full portfolio
            ledger, so the calling engine passes the current signed exposure for
            the relevant symbol. Reduce-only orders are clipped to that opposing
            quantity and become non-executable when no reducible exposure exists.
        """
        requested = float(abs(order.quantity))
        if requested <= 0:
            return 0.0
        if not bool(order.reduce_only):
            return requested

        signed_position = float(current_position)
        if order.side == "BUY":
            if signed_position >= 0:
                return 0.0
            return min(requested, abs(signed_position))
        if order.side == "SELL":
            if signed_position <= 0:
                return 0.0
            return min(requested, abs(signed_position))
        return 0.0

    def _resolve_spread_ticks(
        self,
        order_type: str,
        effective_spread_ticks: Optional[int],
    ) -> int:
        """
        Resolves deterministic spread ticks with optional order-type multipliers.
        """
        return resolve_spread_ticks(
            settings=self.settings,
            order_type=order_type,
            effective_spread_ticks=effective_spread_ticks,
        )

    def _resolve_commission_rate(self, order_type: str) -> float:
        """
        Resolves the per-contract commission rate for the order type.
        """
        return resolve_execution_cost_profile(self.settings, order_type).commission_rate

    def _resolve_bar_fill_details(
        self,
        order: Order,
        order_type: str,
        data_bar: pd.Series,
        execute_at_close: bool,
    ) -> tuple[Optional[float], str]:
        """
        Resolves the deterministic pre-slippage fill price and phase.
        """
        if execute_at_close:
            close_price = float(self._bar_value(data_bar, "close"))
            if order_type == "MARKET":
                return close_price, "CLOSE"
            return None, "CLOSE"

        open_price = float(self._bar_value(data_bar, "open"))
        high_raw = self._bar_value(data_bar, "high", open_price)
        low_raw = self._bar_value(data_bar, "low", open_price)
        high_price = float(high_raw if high_raw is not None else open_price)
        low_price = float(low_raw if low_raw is not None else open_price)

        if order_type == "MARKET":
            return open_price, "OPEN"
        if order_type == "LIMIT":
            return self._resolve_limit_fill_details(order, open_price, high_price, low_price)
        if order_type == "STOP":
            return self._resolve_stop_fill_details(order, open_price, high_price, low_price)
        if order_type == "STOP_LIMIT":
            return self._resolve_stop_limit_fill_details(order, open_price, high_price, low_price)
        return None, "OPEN"

    def preview_fill_price(
        self,
        order: Order,
        data_bar: pd.Series,
        execute_at_close: bool = False,
        current_position: float = 0.0,
    ) -> Optional[float]:
        """
        Returns the pre-slippage fill price without mutating order state.

        Methodology:
        Single-engine OCO coordination needs a deterministic "would this fill?"
        probe before choosing a winning sibling. This helper intentionally
        mirrors the real bar-fill logic while avoiding status transitions such
        as FILLED / REJECTED / CANCELLED during preview.
        """
        order_type = str(order.order_type).upper()
        if order.quantity <= 0:
            return None
        if order_type == "LIMIT" and order.limit_price is None:
            return None
        if order_type == "STOP" and order.stop_price is None:
            return None
        if order_type == "STOP_LIMIT":
            if order.stop_price is None or order.limit_price is None:
                return None
        if order_type not in {"MARKET", "LIMIT", "STOP", "STOP_LIMIT"}:
            return None
        if self._resolve_executable_quantity(order, current_position) <= 0:
            return None
        price, _ = self._resolve_bar_fill_details(
            order=order,
            order_type=order_type,
            data_bar=data_bar,
            execute_at_close=execute_at_close,
        )
        return price

    @staticmethod
    def _bar_value(data_bar: Any, key: str, default: Optional[float] = None) -> Optional[float]:
        """
        Reads a field from either a pandas Series or a FastBar-like object.
        """
        if hasattr(data_bar, "get"):
            return data_bar.get(key, default)
        try:
            return data_bar[key]
        except Exception:
            return default

    @staticmethod
    def _resolve_limit_fill_details(
        order: Order,
        open_price: float,
        high_price: float,
        low_price: float,
    ) -> tuple[Optional[float], str]:
        """
        Resolves a gap-aware limit-order fill price from a single OHLC bar.
        """
        limit_price = float(order.limit_price)
        if order.side == "BUY":
            if open_price <= limit_price:
                return open_price, "OPEN"
            if low_price <= limit_price:
                return limit_price, "INTRABAR"
            return None, "OPEN"

        if open_price >= limit_price:
            return open_price, "OPEN"
        if high_price >= limit_price:
            return limit_price, "INTRABAR"
        return None, "OPEN"

    @staticmethod
    def _resolve_stop_fill_details(
        order: Order,
        open_price: float,
        high_price: float,
        low_price: float,
    ) -> tuple[Optional[float], str]:
        """
        Resolves a gap-aware stop-order fill price from a single OHLC bar.
        """
        stop_price = float(order.stop_price)
        if order.side == "BUY":
            if open_price >= stop_price:
                return open_price, "OPEN"
            if high_price >= stop_price:
                return stop_price, "INTRABAR"
            return None, "OPEN"

        if open_price <= stop_price:
            return open_price, "OPEN"
        if low_price <= stop_price:
            return stop_price, "INTRABAR"
        return None, "OPEN"

    def _resolve_stop_limit_fill_details(
        self,
        order: Order,
        open_price: float,
        high_price: float,
        low_price: float,
    ) -> tuple[Optional[float], str]:
        """
        Resolves a deterministic stop-limit fill price from a single OHLC bar.

        The conservative policy is used whenever the bar proves triggerability
        but does not prove the exact path.
        """
        if order.side == "BUY":
            if open_price >= float(order.stop_price):
                if open_price <= float(order.limit_price):
                    return open_price, "OPEN"
                return None, "OPEN"
            if high_price >= float(order.stop_price) and low_price <= float(order.limit_price):
                return float(order.limit_price), "INTRABAR"
            return None, "OPEN"

        if open_price <= float(order.stop_price):
            if open_price >= float(order.limit_price):
                return open_price, "OPEN"
            return None, "OPEN"
        if low_price <= float(order.stop_price) and high_price >= float(order.limit_price):
            return float(order.limit_price), "INTRABAR"
        return None, "OPEN"

    def _process_trades(self, fill: Fill):
        """
        Reconciles fills into completed Trades (Round-trips) for analytics.
        
        Methodology:
        Applies FIFO matching logic against open positions. 
        Safely calculates continuous multi-fill Net PnL distributions, accounting 
        for proportionate commissions and asset multipliers.
        
        Args:
            fill: The recently executed Fill to match against existing Open tracking metrics.
        """
        symbol = fill.order.symbol
        if symbol not in self._positions:
            self._positions[symbol] = []
            
        fill_qty = fill.order.quantity
        fill_price = fill.fill_price
        fill_comm = fill.commission
        fill_time = fill.timestamp
        remaining_qty = fill.order.quantity
        
        side = 1 if fill.order.side == 'BUY' else -1
        new_open_positions = []
        
        for open_fill in self._positions[symbol]:
            if remaining_qty == 0:
                new_open_positions.append(open_fill)
                continue
                
            open_qty = open_fill.order.quantity
            open_side = 1 if open_fill.order.side == 'BUY' else -1
            
            if side == open_side:
                new_open_positions.append(open_fill)
                continue
                
            match_qty = min(abs(remaining_qty), abs(open_qty))
            entry_price = open_fill.fill_price
            spec = self.settings.get_instrument_spec(symbol)
            multiplier = spec["multiplier"]
            
            # Executed prices already include entry/exit slippage, so this base
            # realized PnL is post-slippage by construction.
            if open_side == 1:
                pnl = (fill_price - entry_price) * match_qty * multiplier
                direction = 'LONG'
            else:
                pnl = (entry_price - fill_price) * match_qty * multiplier
                direction = 'SHORT'
            
            # Approximate proportional commission for the matched chunk
            entry_comm_per_share = open_fill.commission / abs(open_fill.order.quantity) if open_fill.order.quantity != 0 else 0
            exit_comm_per_share = fill_comm / abs(fill_qty) if fill_qty != 0 else 0
            
            trade_comm = (entry_comm_per_share + exit_comm_per_share) * match_qty
            entry_slippage_per_unit = abs(open_fill.slippage) * multiplier
            exit_slippage_per_unit = abs(fill.slippage) * multiplier
            trade_slippage = (entry_slippage_per_unit + exit_slippage_per_unit) * match_qty
            # Keep slippage as an explicit decomposition field only. Subtracting
            # it again here would double count execution friction because
            # `pnl` already reflects the slipped executed prices.
            net_pnl = pnl - trade_comm
            
            self.trades.append(Trade(
                symbol=symbol,
                entry_price=entry_price,
                exit_price=fill_price,
                quantity=match_qty,
                direction=direction,
                entry_time=open_fill.timestamp,
                exit_time=fill_time,
                pnl=net_pnl,
                commission=trade_comm,
                slippage=trade_slippage,
                exit_reason=fill.order.reason,
                entry_signal_time=open_fill.order.timestamp
            ))
            
            # Reduce matched quantities from ongoing open position trackers
            if abs(remaining_qty) >= abs(open_qty):
                remaining_qty = (abs(remaining_qty) - abs(open_qty)) * side
            else:
                residue = (abs(open_qty) - abs(remaining_qty)) * open_side
                residue_fill = self._clone_fill_with_quantity(open_fill, residue)
                new_open_positions.append(residue_fill)
                remaining_qty = 0
        
        # Track any remaining unmatched execution quantities as new open positions
        if remaining_qty != 0:
            new_fill_tracker = self._clone_fill_with_quantity(fill, remaining_qty)
            new_open_positions.append(new_fill_tracker)
            
        self._positions[symbol] = new_open_positions

    def _clone_fill_with_quantity(self, fill: Fill, quantity: float) -> Fill:
        """
        Clones a fill tracker with proportional total costs for a new quantity.

        Methodology:
        Open-position residue objects are accounting trackers, not new market
        executions. They preserve the original fill timestamp and execution
        price. `commission` and signed cash `cost` are scaled to the remaining
        quantity because they are aggregate fill totals. `slippage` is
        intentionally left unchanged because Fill stores it as a per-contract
        price-unit adjustment; scaling it here would understate residue slippage
        on later matched trade fragments.

        Args:
            fill: Original fill object.
            quantity: Signed quantity to keep on the cloned tracker.

        Returns:
            A cloned Fill with scaled aggregate fields for the requested quantity.
        """
        original_qty = abs(fill.order.quantity)
        scaled_fill = replace(fill)
        scaled_fill.order = replace(fill.order)
        scaled_fill.order.quantity = quantity

        if original_qty <= 0:
            scaled_fill.commission = 0.0
            scaled_fill.cost = 0.0
            return scaled_fill

        qty_ratio = abs(quantity) / original_qty
        scaled_fill.commission = float(fill.commission) * qty_ratio
        scaled_fill.cost = float(fill.cost) * qty_ratio
        return scaled_fill
