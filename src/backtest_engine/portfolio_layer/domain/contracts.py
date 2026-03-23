"""
src/backtest_engine/portfolio_layer/domain/contracts.py

Top-level portfolio configuration contracts.

Responsibility: PortfolioConfig and StrategySlot define the shape of user-
facing YAML configuration only.  No computation or I/O here.

Execution settings (commission_rate, spread_ticks, spread_mode) and kill-switch
thresholds (max_daily_loss, max_drawdown_pct, max_account_floor) live in
BacktestSettings (settings.py) to avoid duplication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type

@dataclass
class StrategySlot:
    """
    Wires a strategy class to a set of symbols with an allocation weight.

    Attributes:
        strategy_class: Any class that inherits from BaseStrategy.
        symbols: Tickers this strategy slot trades (e.g. ['ES', 'NQ']).
        weight: Capital fraction allocated to this slot (0-1).
                All slot weights must sum to 1.0.
        expected_duty_cycle: Ex-ante expectation of squared normalized
                exposure, E[(position / max_position)^2]. Used to scale the
                standalone vol budget for slots that are flat or partially
                invested much of the time.
        timeframe: Bar resolution to load for all symbols in this slot.
        params: Optional strategy-level kwargs injected as settings overrides.
                These are written through _PatchedSettings so strategies can
                read them via self.settings.param_name (same as WFO injection).
    """
    strategy_class: Type
    symbols: List[str]
    weight: float
    expected_duty_cycle: float = 1.0
    timeframe: str = "30m"
    params: Dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validates field-level invariants that do not depend on other slots."""
        if not (0.0 < self.expected_duty_cycle <= 1.0):
            raise ValueError(
                f"expected_duty_cycle must be in (0, 1], got {self.expected_duty_cycle}"
            )


@dataclass
class PortfolioConfig:
    """
    Top-level portfolio backtest configuration.

    Only portfolio-specific settings live here.  Execution parameters
    (commission_rate, spread_ticks, spread_mode) and risk kill-switch thresholds
    are read from BacktestSettings to keep a single source of truth.

    Attributes:
        slots: List of StrategySlots defining the full multi-strat allocation.
        initial_capital: Total portfolio capital in dollars.
        rebalance_frequency: 'intrabar', 'daily', or 'weekly'.
        target_portfolio_vol: Annualised portfolio volatility target (e.g. 0.10 = 10 %).
        vol_lookback_bars: Rolling window (bars) used to estimate realised vol per symbol.
        max_weight_expansion: Relative cap on duty-cycle-driven sizing
            expansion. For example, 4.0 caps the multiplier at 2x because
            slot risk scales with sqrt(weight * expansion).
        max_contracts_per_slot: Optional hard cap on contracts per (slot, symbol) pair.
    """
    slots: List[StrategySlot]
    initial_capital: float
    rebalance_frequency: str
    target_portfolio_vol: float = 0.10
    vol_lookback_bars: int = 20
    max_weight_expansion: float = 4.0
    max_contracts_per_slot: Optional[int] = None
    benchmark_symbol: Optional[str] = "ES"   # Buy-and-hold benchmark (None to disable)

    def __post_init__(self) -> None:
        """Validates field-level invariants that do not require aggregate checks."""
        if self.max_weight_expansion < 1.0:
            raise ValueError(
                f"max_weight_expansion must be >= 1.0, got {self.max_weight_expansion}"
            )

    def validate(self) -> None:
        """
        Validates config invariants before the engine starts.

        Raises:
            ValueError: If weights do not sum to 1 or any slot has no symbols.
        """
        total_weight = sum(s.weight for s in self.slots)
        if abs(total_weight - 1.0) > 1e-2:
            raise ValueError(
                f"StrategySlot weights must sum to 1.0, got {total_weight:.4f}"
            )
        for slot in self.slots:
            if not slot.symbols:
                raise ValueError(f"StrategySlot {slot.strategy_class.__name__} has no symbols.")
            if slot.weight <= 0:
                raise ValueError(f"StrategySlot {slot.strategy_class.__name__} has weight <= 0.")
            if not (0.0 < slot.expected_duty_cycle <= 1.0):
                raise ValueError(
                    "StrategySlot "
                    f"{slot.strategy_class.__name__} expected_duty_cycle must be in (0, 1], "
                    f"got {slot.expected_duty_cycle}"
                )
        if not (0.0 < self.target_portfolio_vol <= 1.0):
            raise ValueError(
                f"target_portfolio_vol must be in (0, 1], got {self.target_portfolio_vol}"
            )
        if self.vol_lookback_bars < 2:
            raise ValueError("vol_lookback_bars must be >= 2.")
        if self.max_weight_expansion < 1.0:
            raise ValueError(
                f"max_weight_expansion must be >= 1.0, got {self.max_weight_expansion}"
            )
        if self.max_contracts_per_slot is not None and self.max_contracts_per_slot < 1:
            raise ValueError("max_contracts_per_slot must be >= 1.")
