"""
src/backtest_engine/portfolio_layer/allocation/allocator.py

Capital allocation and contract sizing for the portfolio backtester.

Responsibility: Given total equity, strategy weights, signals, and recent
price history, compute TargetPosition quantities for each (slot, symbol) pair
using volatility-targeting methodology.

Methodology (per slot, per symbol):
    1.  dc_multiplier      = min(1 / sqrt(expected_duty_cycle),
                                 sqrt(max_weight_expansion))
    2.  slot_risk_budget   = (total_equity * target_portfolio_vol
                              * sqrt(slot.weight) * dc_multiplier)
    3.  ticker_risk_budget = slot_risk_budget / number_of_symbols_in_slot
    4.  instrument_vol     = annualised rolling stddev of close-to-close returns
                             over the last vol_lookback_bars bars.
    5.  contract_dollar_vol = instrument_vol * price * multiplier
    6.  raw_contracts      = ticker_risk_budget / contract_dollar_vol
    7.  contracts          = round(raw_contracts)
    8.  contracts          = min(contracts, margin_capacity_contracts)
    9.  contracts          = min(contracts, max_contracts_per_slot) if cap is set
    10. target_qty         = contracts * signal.direction for OPEN/HOLD/REVERSE,
                             or 0 for explicit CLOSE intent

IMPORTANT - Zero Cross-Correlation Assumption:
    Slot weights are aggregated via sqrt(weight) scaling, which is correct only
    when slot returns are uncorrelated (IID baseline from Modern Portfolio
    Theory). For correlated instruments (for example ES and NQ), simultaneous
    drawdowns can cause realized portfolio volatility to exceed
    target_portfolio_vol. Correlation-adjusted overlays belong in the future
    PortfolioRiskOverlay layer.

The key denominator is the annualised dollar volatility of one full contract:
`annualised_vol * price * multiplier`. Tick size is relevant for execution and
slippage simulation, but it is not the correct denominator for volatility-
targeted contract sizing.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from ..domain.contracts import PortfolioConfig
from ..domain.signals import (
    BRIDGE_INTENT_CLOSE,
    StrategySignal,
    TargetPosition,
)


# Fallback annualisation factor used when the engine doesn't supply bars_per_year.
# Overridden at runtime by PortfolioBacktestEngine with a value derived from
# the actual data span (total_bars / calendar_years).
_BARS_PER_YEAR_FALLBACK: int = 252 * 13   # conservative 30-min futures assumption

class Allocator:
    """
    Converts strategy signals into sized target contract quantities.

    Uses volatility-targeting with slot risk budgets. Slot weights are treated
    as portfolio risk weights, not as a second capital haircut on the target
    volatility itself. For an equal-risk portfolio, each slot receives
    `target_portfolio_vol * sqrt(weight)` of standalone annualised volatility
    before any static duty-cycle normalization is applied.

    A simple margin-capacity gate prevents the target quantity from exceeding
    what the slot equity can realistically support in live futures trading.
    An optional hard cap can still be applied from config when desired.
    """

    def __init__(self, config: PortfolioConfig) -> None:
        """
        Args:
            config: Validated PortfolioConfig holding vol-targeting parameters.
        """
        self._config = config

    # ── Public API ─────────────────────────────────────────────────────────────

    def compute_targets(
        self,
        signals: List[StrategySignal],
        total_equity: float,
        current_prices: Dict[str, float],
        instrument_specs: Dict[str, Dict],
        price_history: Dict[Tuple[int, str], pd.Series],
        bars_per_year: int = _BARS_PER_YEAR_FALLBACK,
    ) -> List[TargetPosition]:
        """
        Computes desired target positions for all active signals.

        Methodology:
            See the module docstring for the full sizing formula.
            If instrument vol cannot be estimated (insufficient history or
            zero variance), falls back to 1 contract to avoid zero allocation.
            A zero-direction CLOSE signal always produces target_qty = 0
            (flat). Other intents still size from `direction`.

        Args:
            signals: List of StrategySignals for this bar.
            total_equity: Current portfolio equity (cash + MtM).
            current_prices: Symbol -> latest close price.
            instrument_specs: Symbol -> {multiplier, tick_size}.
            price_history: (slot_id, symbol) -> pd.Series of recent close prices
                           (at least vol_lookback_bars entries).

        Returns:
            List of TargetPosition objects (one per signal).
        """
        targets: List[TargetPosition] = []

        for sig in signals:
            slot      = self._config.slots[sig.slot_id]
            n_tickers = len(slot.symbols)

            # Use weights as portfolio risk budgets. If one slot trades multiple
            # symbols, split that slot-level risk and margin capacity equally.
            slot_weight = float(slot.weight)
            duty_cycle = max(float(slot.expected_duty_cycle), 1e-4)
            max_expansion = float(self._config.max_weight_expansion)
            dc_multiplier = min(
                1.0 / math.sqrt(duty_cycle),
                math.sqrt(max_expansion),
            )
            slot_risk_budget = (
                total_equity
                * self._config.target_portfolio_vol
                * math.sqrt(slot_weight)
                * dc_multiplier
                if slot_weight > 0.0
                else 0.0
            )
            risk_budget_per_ticker = slot_risk_budget / n_tickers if n_tickers > 0 else 0.0
            margin_equity_per_ticker = (total_equity * slot_weight) / n_tickers if n_tickers > 0 else 0.0

            price     = current_prices.get(sig.symbol, 0.0)
            spec      = instrument_specs.get(
                sig.symbol,
                {"multiplier": 1.0, "tick_size": 0.01, "margin_ratio": 1.0},
            )
            multiplier = float(spec.get("multiplier", 1.0))
            margin_ratio = float(spec.get("margin_ratio", 1.0))

            if price > 0 and multiplier > 0 and margin_ratio > 0 and sig.direction != 0:
                vol = self._estimate_vol(sig.slot_id, sig.symbol, price_history, bars_per_year)
                contracts = self._size_contracts(
                    risk_budget_per_ticker,
                    margin_equity_per_ticker,
                    price,
                    multiplier,
                    margin_ratio,
                    vol,
                )
            else:
                contracts = 0

            targets.append(TargetPosition(
                slot_id=sig.slot_id,
                symbol=sig.symbol,
                target_qty=self._resolve_target_quantity(sig, contracts),
                reason=sig.reason,
            ))

        return targets

    @staticmethod
    def _resolve_target_quantity(sig: StrategySignal, contracts: int) -> float:
        """
        Converts a sized signal into the portfolio target quantity.

        Methodology:
            Most bridge intents still size to `contracts * direction`.
            Explicit CLOSE intent is the exception: it flattens the slot even
            when the live position sign and raw exit order side disagree.
        """
        if str(sig.bridge_intent).upper() == BRIDGE_INTENT_CLOSE:
            return 0.0
        return float(contracts * sig.direction)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _estimate_vol(
        self,
        slot_id: int,
        symbol: str,
        price_history: Dict[Tuple[int, str], pd.Series],
        bars_per_year: int = _BARS_PER_YEAR_FALLBACK,
    ) -> float:
        """
        Estimates annualised realised volatility from recent close prices.

        Methodology:
            Computes close-to-close log returns over the last vol_lookback_bars
            bars, takes their standard deviation, and annualises by multiplying
            by sqrt(bars_per_year).  Returns a conservative fallback of 1.0
            (100 % vol, resulting in very small sizing) when data is insufficient.

        Args:
            slot_id: Strategy slot index for series isolation.
            symbol: Instrument ticker.
            price_history: (slot_id, symbol) -> pd.Series of close prices.
            bars_per_year: Annualisation factor from the engine (actual data frequency).

        Returns:
            Annualised volatility estimate (e.g. 0.15 = 15 %).
        """
        series = price_history.get((slot_id, symbol))
        lookback = self._config.vol_lookback_bars

        if series is None or len(series) < lookback + 1:
            return 1.0  # Conservative fallback: will produce minimal sizing.

        closes   = series.iloc[-(lookback + 1):]
        log_rets = np.log(closes / closes.shift(1)).dropna()

        if len(log_rets) < 2:
            return 1.0

        bar_vol = float(np.std(log_rets, ddof=1))
        if bar_vol <= 0.0:
            return 1.0

        return bar_vol * math.sqrt(bars_per_year)

    def _compute_raw_contracts(
        self,
        annual_risk_budget: float,
        price: float,
        multiplier: float,
        annualised_vol: float,
    ) -> float:
        """
        Computes the continuous vol-target contract quantity before rounding.

        Methodology:
            `annualised_vol` is expected to already be annualized by
            `_estimate_vol()`. `annual_risk_budget` is the full annualized
            dollar-volatility budget already assigned to this (slot, ticker),
            and one contract contributes
            `annualised_vol * price * multiplier` of annualized dollar
            volatility. Rounding and hard caps are applied only after this raw
            quantity is computed so the mathematical target remains testable.

        Args:
            annual_risk_budget: Annualized dollar-volatility budget for this
                (slot, ticker).
            price: Current close price of the instrument.
            multiplier: Contract multiplier used to convert price moves to dollars.
            annualised_vol: Estimated annualized volatility (e.g. 0.15).

        Returns:
            Continuous contract quantity before integer conversion.
        """
        if annual_risk_budget <= 0.0 or price <= 0.0 or multiplier <= 0.0 or annualised_vol <= 0.0:
            return 0.0

        contract_dollar_vol = annualised_vol * price * multiplier
        if contract_dollar_vol <= 0.0:
            return 0.0

        return max(0.0, annual_risk_budget / contract_dollar_vol)

    def _size_contracts(
        self,
        annual_risk_budget: float,
        margin_equity: float,
        price: float,
        multiplier: float,
        margin_ratio: float,
        annualised_vol: float,
    ) -> int:
        """
        Computes integer contract count using vol-targeting.

        Methodology:
            First compute the continuous vol-target contract quantity from the
            annualized risk budget and the annualized dollar volatility of one
            contract. The resulting quantity is then clipped by a simple
            margin-capacity limit based on `price * multiplier * margin_ratio`.
            An optional hard cap is applied last.

        Args:
            annual_risk_budget: Annualized dollar volatility budget for this
                (slot, ticker).
            margin_equity: Dollar capital reserved to support margin for this
                (slot, ticker).
            price: Current close price of the instrument.
            multiplier: Contract multiplier used to convert price moves to dollars.
            margin_ratio: Fraction of notional required as margin.
            annualised_vol: Estimated annualized volatility (e.g. 0.15).

        Returns:
            Integer contract count (>= 0), rounded and constrained by
            margin capacity plus the optional max_contracts_per_slot.
        """
        raw_contracts = self._compute_raw_contracts(
            annual_risk_budget=annual_risk_budget,
            price=price,
            multiplier=multiplier,
            annualised_vol=annualised_vol,
        )
        contracts = max(0, round(raw_contracts))
        margin_per_contract = price * multiplier * margin_ratio
        if margin_per_contract > 0.0:
            contracts = min(contracts, max(0, math.floor(margin_equity / margin_per_contract)))

        if self._config.max_contracts_per_slot is not None:
            contracts = min(contracts, self._config.max_contracts_per_slot)

        return contracts
