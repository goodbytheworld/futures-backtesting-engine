"""
Portfolio tracking for the backtest engine.
"""

from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd

from ..execution import Fill
from ..config import BacktestSettings


class Portfolio:
    """
    Tracks cash, open positions, and portfolio value history.

    Methodology:
        Cash accounting uses full notional: buying a contract deducts
        price * qty * multiplier from cash.  This is conservative (no
        margin leverage) and makes capital usage transparent.
    """

    def __init__(self, settings: BacktestSettings) -> None:
        self.settings = settings
        self.initial_capital = settings.initial_capital
        self.current_cash: float = self.initial_capital
        self.positions: Dict[str, float] = {}   # Symbol → signed quantity
        self.holdings_value: float = 0.0
        self.total_value: float = self.initial_capital
        self.history: List[Dict] = []

    def update(self, fill: Optional[Fill], current_prices: Dict[str, float]) -> None:
        """
        Updates cash, positions, and total portfolio value.

        Args:
            fill: Newly executed fill; None for a mark-to-market only update.
            current_prices: Latest close prices keyed by symbol.
        """
        if fill is not None:
            symbol = fill.order.symbol
            spec = self.settings.get_instrument_spec(symbol)
            multiplier = spec["multiplier"]
            notional = fill.fill_price * fill.order.quantity * multiplier

            if fill.order.side == "BUY":
                self.current_cash -= notional + fill.commission
                self.positions[symbol] = self.positions.get(symbol, 0.0) + fill.order.quantity
            else:  # SELL
                self.current_cash += notional - fill.commission
                self.positions[symbol] = self.positions.get(symbol, 0.0) - fill.order.quantity

        # Mark-to-market open positions
        self.holdings_value = 0.0
        for sym, qty in self.positions.items():
            if qty != 0 and sym in current_prices:
                spec = self.settings.get_instrument_spec(sym)
                self.holdings_value += qty * current_prices[sym] * spec["multiplier"]

        self.total_value = self.current_cash + self.holdings_value

    def record_snapshot(self, timestamp: datetime) -> None:
        """Appends the current portfolio state to the history log."""
        self.history.append(
            {
                "timestamp": timestamp,
                "cash": self.current_cash,
                "holdings": self.holdings_value,
                "total_value": self.total_value,
            }
        )

    def get_history_df(self) -> pd.DataFrame:
        """Returns portfolio history as a DataFrame indexed by timestamp."""
        if not self.history:
            return pd.DataFrame()
        df = pd.DataFrame(self.history)
        df.set_index("timestamp", inplace=True)
        return df
