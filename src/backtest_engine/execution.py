from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, replace
from datetime import datetime
import pandas as pd
import random

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
    timestamp: datetime = field(default_factory=datetime.utcnow)

@dataclass
class Fill:
    """
    Represents a finalized trade execution against the market.
    """
    order: Order
    fill_price: float
    commission: float
    slippage: float
    cost: float
    timestamp: datetime
    
@dataclass
class Trade:
    """
    Represents a completed round-trip trade (Entry + Exit) for analytics scoring.
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
    exit_reason: str = 'SIGNAL'
    entry_signal_time: Optional[datetime] = None

class ExecutionHandler:
    """
    Handles order execution tracking and simulates fills into Round-trip Trades.
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
        self._random = random.Random(getattr(settings, "random_seed", 42))
        
        # Position tracking for Trade matching (FIFO basis)
        self._positions: Dict[str, List[Fill]] = {} 

    def execute_order(self, order: Order, data_bar: pd.Series, execute_at_close: bool = False) -> Optional[Fill]:
        """
        Simulates order execution with slippage and commission constraints.
        
        Methodology:
        Derives an execution price realistically adjusted by market constraints. 
        Applies a randomized slippage model based on tick sizes and deduces fixed rate commissions.
        
        Args:
            order: The Order object to execute.
            data_bar: The current OHLCV bar representing the market state at execution.
            execute_at_close: Evaluates execution against close prices if True, open prices otherwise.
            
        Returns:
            The executed Fill object, or None if execution fails.
        """
        price = data_bar['close'] if execute_at_close else data_bar['open']
        
        if order.order_type == 'MARKET':
            price = data_bar['close'] if execute_at_close else data_bar['open']
        
        spec = self.settings.get_instrument_spec(order.symbol)
        max_ticks = getattr(self.settings, 'max_slippage_ticks', 1)
        
        actual_slippage_ticks = self._random.randint(0, max_ticks)
        slippage = actual_slippage_ticks * spec["tick_size"]
        
        executed_price = price + slippage if order.side == 'BUY' else price - slippage
        commission = abs(order.quantity) * self.settings.commission_rate
        cost = (executed_price * order.quantity) if order.side == 'BUY' else -(executed_price * order.quantity)
        
        fill = Fill(
            order=order,
            fill_price=executed_price,
            commission=commission,
            slippage=slippage,
            cost=cost,
            timestamp=data_bar.name if isinstance(data_bar.name, datetime) else order.timestamp
        )
        self.fills.append(fill)
        self._process_trades(fill)
        return fill

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
            
            # Calculate Base PnL honoring whether the trade entered as Long or Short
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
                exit_reason=fill.order.reason,
                entry_signal_time=open_fill.order.timestamp
            ))
            
            # Reduce matched quantities from ongoing open position trackers
            if abs(remaining_qty) >= abs(open_qty):
                remaining_qty = (abs(remaining_qty) - abs(open_qty)) * side
            else:
                residue = (abs(open_qty) - abs(remaining_qty)) * open_side
                open_fill.order.quantity = residue
                new_open_positions.append(open_fill)
                remaining_qty = 0
        
        # Track any remaining unmatched execution quantities as new open positions
        if remaining_qty != 0:
            new_fill_tracker = replace(fill)
            new_fill_tracker.order = replace(fill.order)
            new_fill_tracker.order.quantity = remaining_qty
            new_open_positions.append(new_fill_tracker)
            
        self._positions[symbol] = new_open_positions
