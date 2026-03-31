"""
src/backtest_engine/portfolio_layer/engine/engine.py

PortfolioBacktestEngine — multi-strategy, multi-asset event loop.

No-lookahead contract (same as BacktestEngine):
    1. Data loaded for all (slot, symbol) pairs.
    2. Iterate bar-by-bar on the union timeline.
    3. Strategies see bar[t] close.
    4. Signals from bar[t] -> orders fill at open[t+1].
    5. MtM and equity recomputed after fills.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

import pandas as pd

from src.backtest_engine.config import BacktestSettings
from src.backtest_engine.execution import Order
from src.backtest_engine.execution.spread_model import compute_spread_ticks
from src.backtest_engine.execution.time_controls import is_session_active, parse_hhmm
from src.data.data_lake import DataLake

from ..domain.contracts import PortfolioConfig
from ..domain.orders import PendingPortfolioOrder
from ..domain.signals import RequestedOrderIntent, StrategySignal, TargetPosition
from ..execution.portfolio_book import PortfolioBook
from ..execution.order_book import PortfolioOrderBook
from ..allocation.allocator import Allocator
from ..execution.strategy_runner import StrategyRunner
from ..reporting.results import save_portfolio_results
from ..scheduling.scheduler import make_scheduler


class PortfolioBacktestEngine:
    """
    Event-driven portfolio backtest engine.

    Methodology:
        Builds a unified timeline (union of all loaded bar timestamps).
        At each bar:
          A. Fill pending orders at open[t] (strict no-lookahead).
             Orders are CARRIED FORWARD through gap bars — never silently dropped.
          B. Mark-to-market all positions (using last-known price on gap bars).
          C. Risk-limit check (daily loss, drawdown, account floor).
          D. Scheduler decides whether to rebalance this bar.
          E. If rebalancing and not halted, call StrategyRunner.collect_signals().
          F. Call Allocator.compute_targets() -> List[TargetPosition].
          G. Compute order deltas vs current positions.
          H. Queue delta orders for execution at open[t+1].
          I. EOD forced close (weekend-safe).
          J. Record portfolio snapshot.

        Shared-capital invariant:
            All positions share a single cash pool.  No slot can run more
            capital than its weight allocation of total_equity.

        Kill-switches (from BacktestSettings):
            max_daily_loss      — daily PnL drawdown halt (temporary, resets next day).
            max_drawdown_pct    — peak-to-trough drawdown permanent halt.
            max_account_floor   — absolute equity level permanent halt.

        EOD weekend guard:
            A Friday-to-Monday date transition is treated as an EOD boundary,
            preventing positions from being carried into the weekend.
    """

    def __init__(
        self,
        config: PortfolioConfig,
        settings: Optional[BacktestSettings] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> None:
        """
        Args:
            config: Validated PortfolioConfig defining slots and weights.
            settings: Optional BacktestSettings override.
            start_date: Optional backtest start filter.
            end_date: Optional backtest end filter.
        """
        config.validate()
        self.config     = config
        if settings is None:
            raise ValueError("BacktestSettings must be provided via Dependency Injection.")
        self.settings   = settings
        self.start_date = start_date
        self.end_date   = end_date

        self.book      = PortfolioBook(config.initial_capital)
        self.allocator = Allocator(config)
        self.data_lake = DataLake(self.settings)
        self.scheduler = make_scheduler(config.rebalance_frequency)

        from src.backtest_engine.execution import ExecutionHandler

        # One ExecutionHandler per slot — commission/slippage from the config package
        self._execution_handlers: Dict[int, Any] = {
            i: ExecutionHandler(self.settings) for i in range(len(config.slots))
        }
        # Live reference to each handler's trade list
        self._slot_trades: Dict[int, List[Any]] = {
            i: self._execution_handlers[i].trades for i in range(len(config.slots))
        }

        # Loaded data: (slot_id, symbol) -> DataFrame
        self._data_map: Dict[Tuple[int, str], pd.DataFrame] = {}
        # Symbol -> last-available bar lookup: updated as bars are visited
        self._last_bars: Dict[Tuple[int, str], pd.Series] = {}
        # Optional lower-timeframe replay data used only for explicit
        # intrabar OCO conflict resolution.
        self._intrabar_data_map: Dict[Tuple[int, str], pd.DataFrame] = {}

        # Computed once from real data after _load_data(); passed to Allocator.
        self._bars_per_year: int = 3276  # Conservative default (30m, 252d x 13 bars)

        # Daily risk state (mirrors BacktestEngine._check_risk_limits)
        self._last_date: Optional[date] = None
        self._equity_at_day_start: float = config.initial_capital
        self._peak_equity: float = config.initial_capital
        self.trading_halted_today: bool = False
        self.trading_halted_permanently: bool = False
        self._eod_closed_dates: set[date] = set()

    # ── Risk management ────────────────────────────────────────────────────────

    def _check_risk_limits(self, current_date: date) -> None:
        """
        Evaluates daily loss, max drawdown, and account floor limits.

        Methodology:
            Checks are performed once per day boundary and after each bar.
            Breached limits set halt flags which cause the loop to skip
            strategy logic and force liquidation.

        Args:
            current_date: Current bar's calendar date.
        """
        if self.trading_halted_permanently:
            return

        # Reset daily tracking on new day
        if self._last_date != current_date:
            self._last_date = current_date
            self._equity_at_day_start = self.book.total_equity
            self.trading_halted_today = False

        daily_pnl = self.book.total_equity - self._equity_at_day_start

        if self.settings.max_daily_loss is not None:
            if daily_pnl < -self.settings.max_daily_loss:
                if not self.trading_halted_today:
                    print(
                        f"[Portfolio Risk] Daily loss limit hit "
                        f"({daily_pnl:.0f} < -{self.settings.max_daily_loss}). "
                        f"Halting today."
                    )
                    self.trading_halted_today = True

        if self.settings.max_drawdown_pct is not None:
            drawdown_pct = (
                (self._peak_equity - self.book.total_equity) / self._peak_equity
                if self._peak_equity > 0 else 0.0
            )
            if drawdown_pct > self.settings.max_drawdown_pct:
                print(
                    f"[Portfolio Risk] Max drawdown hit "
                    f"({drawdown_pct:.1%} > {self.settings.max_drawdown_pct:.1%}). "
                    f"Permanent halt."
                )
                self.trading_halted_permanently = True

        if self.settings.max_account_floor is not None:
            if self.book.total_equity <= self.settings.max_account_floor:
                print(
                    f"[Portfolio Risk] Account floor hit "
                    f"({self.book.total_equity:.0f}). Permanent halt."
                )
                self.trading_halted_permanently = True

        self._peak_equity = max(self._peak_equity, self.book.total_equity)

    def _liquidate_slot(
        self,
        slot_id: int,
        symbol: str,
        qty: float,
        bar: "pd.Series",
        execute_at_close: bool = False,
        reason: str = "RISK_LIQ",
        effective_spread_ticks: Optional[int] = None,
    ) -> None:
        """
        Liquidates a single (slot, symbol) position at the given bar.

        Args:
            slot_id: Slot index.
            symbol: Instrument ticker.
            qty: Current signed quantity (non-zero guaranteed by caller).
            bar: Current bar pd.Series (for fill simulation).
            execute_at_close: Fill at close price if True, else open.
            reason: Tag written to the order.
            effective_spread_ticks: Pre-computed tick count from the spread model.
        """
        side = "SELL" if qty > 0 else "BUY"
        self._execute_order(
            slot_id, symbol, side, abs(qty), bar,
            execute_at_close=execute_at_close,
            reason=reason,
            effective_spread_ticks=effective_spread_ticks,
            reduce_only=True,
        )

    # ── Data loading ───────────────────────────────────────────────────────────

    def _load_data(self) -> None:
        """
        Loads OHLCV data for every (slot_id, symbol) pair.

        Also computes bars_per_year from the actual data span so the
        Allocator's vol annualisation is derived from real bar frequency
        rather than a hardcoded constant.

        Raises:
            RuntimeError: If any required data is missing from the data lake.
        """
        for slot_id, slot in enumerate(self.config.slots):
            for symbol in slot.symbols:
                df = self.data_lake.load(
                    symbol,
                    timeframe=slot.timeframe,
                    start_date=self.start_date,
                    end_date=self.end_date,
                )
                if df.empty:
                    raise RuntimeError(
                        f"[Portfolio] No data for {symbol} @ {slot.timeframe}. "
                        f"Run: python run.py --download {symbol}"
                    )
                self._data_map[(slot_id, symbol)] = df

        # Estimate bars_per_year from the first available DataFrame.
        # Formula: total_bars / total_calendar_years (using date span).
        first_df = next(iter(self._data_map.values()))
        if len(first_df) >= 2:
            span_days = (first_df.index[-1] - first_df.index[0]).total_seconds() / 86400
            span_years = max(span_days / 365.25, 1e-6)
            self._bars_per_year = max(1, round(len(first_df) / span_years))
        print(f"[Portfolio] bars_per_year estimate: {self._bars_per_year:,}")

    def _intrabar_conflict_replay_enabled(self) -> bool:
        """
        Returns True when lower-timeframe conflict replay is explicitly enabled.
        """
        return (
            str(self.settings.intrabar_conflict_resolution).lower() == "lower_timeframe"
            and bool(self.settings.intrabar_resolution_timeframe)
        )

    def _get_intrabar_conflict_data(
        self,
        slot_id: int,
        symbol: str,
    ) -> Optional[pd.DataFrame]:
        """
        Returns lower-timeframe replay data for one (slot, symbol) on demand.

        Methodology:
            The engine stays on the primary strategy timeframe during normal
            execution. Lower-timeframe data is loaded only when an actual same-
            bar protective OCO conflict needs replay. Missing replay data is a
            valid outcome and must fall back to the pessimistic stop-first
            policy.
        """
        if not self._intrabar_conflict_replay_enabled():
            return None

        cache_key = (slot_id, symbol)
        if cache_key in self._intrabar_data_map:
            return self._intrabar_data_map[cache_key]

        timeframe = str(self.settings.intrabar_resolution_timeframe)
        df = self.data_lake.load(
            symbol,
            timeframe=timeframe,
            start_date=self.start_date,
            end_date=self.end_date,
        )
        if df.empty:
            self._intrabar_data_map[cache_key] = pd.DataFrame()
        else:
            self._intrabar_data_map[cache_key] = df
        return self._intrabar_data_map[cache_key]

    # ── Spread helpers ─────────────────────────────────────────────────────────

    def _effective_spread_ticks(
        self,
        slot_id: int,
        symbol: str,
        price_history: Dict[Tuple[int, str], "pd.Series"],
        up_to_ts: Any,
    ) -> Optional[int]:
        """
        Computes the deterministic spread tick count for a symbol at the current bar.

        Methodology:
            For static mode, returns None so ExecutionHandler reads
            settings.spread_ticks directly.
            For adaptive_volatility mode, slices close history strictly before
            up_to_ts (no-lookahead: execution happens at open[ts], so close[ts]
            is not yet observable).  Mirrors the single engine which uses
            closes[:bar_index] to exclude the current bar.

        Args:
            slot_id: Slot index for strategy-local market data context.
            symbol: Instrument ticker.
            price_history: Mapping of (slot_id, symbol) to full close-price Series.
            up_to_ts: Current bar timestamp.  Close at this timestamp is excluded.

        Returns:
            Integer tick count for adaptive mode, or None for static mode.
        """
        if self.settings.spread_mode != "adaptive_volatility":
            return None

        series = price_history.get((slot_id, symbol))
        if series is None:
            return self.settings.spread_ticks

        # Exclude the close at up_to_ts: that bar's close is not yet available
        # when the order fills at open[ts].  This mirrors closes[:bar_index] in
        # the single engine which is a Python slice (exclusive upper bound).
        closes = series.loc[:up_to_ts]
        if up_to_ts in series.index:
            closes = closes.iloc[:-1]

        return compute_spread_ticks(
            mode=self.settings.spread_mode,
            base_ticks=self.settings.spread_ticks,
            closes=closes,
            vol_step_pct=self.settings.spread_volatility_step_pct,
            step_multiplier=self.settings.spread_step_multiplier,
            vol_lookback=self.settings.spread_vol_lookback,
            vol_baseline_lookback=self.settings.spread_vol_baseline_lookback,
        )

    # ── Execution simulation ───────────────────────────────────────────────────

    def _execute_order(
        self,
        slot_id: int,
        symbol: str,
        side: str,
        quantity: float,
        bar: "pd.Series",
        execute_at_close: bool = False,
        reason: str = "PORTFOLIO_SYNC",
        effective_spread_ticks: Optional[int] = None,
        reduce_only: bool = False,
        order_type: str = "MARKET",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: str = "DAY",
    ) -> bool:
        """
        Simulates a fill via ExecutionHandler and applies it to PortfolioBook.

        Delegates to the slot's ExecutionHandler to generate a proper Trade
        object (same FIFO matching as the single-asset engine), then writes
        the fill into the shared PortfolioBook.

        Args:
            slot_id: Slot index.
            symbol: Instrument ticker.
            side: 'BUY' or 'SELL'.
            quantity: Absolute quantity to trade.
            bar: Current bar pd.Series for price reference.
            execute_at_close: Fill at close price if True, else open.
            reason: Tag written to the order.
            effective_spread_ticks: Pre-computed tick count from the spread model.
                                    If None, ExecutionHandler reads settings.spread_ticks.
            reduce_only: Carries reduce-only intent into the shared Order record.
            order_type: Execution order type passed into the shared handler.
            limit_price: Optional limit price for LIMIT / STOP_LIMIT orders.
            stop_price: Optional stop price for STOP / STOP_LIMIT orders.
            time_in_force: Time-in-force passed into the shared handler.
        """
        spec = self.settings.get_instrument_spec(symbol)
        multiplier = spec["multiplier"]

        order = Order(
            symbol=symbol,
            quantity=abs(quantity),
            side=side,
            order_type=order_type,
            reason=reason,
            timestamp=bar.name if hasattr(bar, "name") else None,
            reduce_only=reduce_only,
            limit_price=limit_price,
            stop_price=stop_price,
            time_in_force=time_in_force,
        )

        handler = self._execution_handlers[slot_id]
        fill = handler.execute_order(
            order, bar,
            execute_at_close=execute_at_close,
            effective_spread_ticks=effective_spread_ticks,
        )

        if fill:
            signed_qty = quantity if side == "BUY" else -quantity
            self.book.apply_fill(
                slot_id=slot_id,
                symbol=symbol,
                fill_price=fill.fill_price,
                quantity=signed_qty,
                commission=fill.commission,
                multiplier=multiplier,
                timestamp=fill.timestamp,
            )
            return True
        return False

    # ── Order delta computation ────────────────────────────────────────────────

    def _compute_orders(
        self,
        targets: List[TargetPosition],
        pending_orders: List[PendingPortfolioOrder],
        signal_templates: Optional[Dict[Tuple[int, str], StrategySignal]] = None,
        replacement_keys: Optional[set[Tuple[int, str]]] = None,
    ) -> List[PendingPortfolioOrder]:
        """
        Computes order deltas from target positions vs current holdings + pending orders.

        Args:
            targets: Desired target positions.
            pending_orders: Already-active pending orders for netting.
            signal_templates: Optional fresh signal metadata from the current bar.

        Returns:
            List of PendingPortfolioOrder objects.
        """
        pending_qty: Dict[Tuple[int, str], float] = {}
        resting_template_keys: set[Tuple[int, str]] = set()
        signal_templates = signal_templates or {}
        replacement_keys = replacement_keys or set()
        for order in pending_orders:
            key = (order.slot_id, order.symbol)
            if key in replacement_keys and order.owns_resting_execution_state:
                continue
            pending_qty[key] = pending_qty.get(key, 0.0) + order.signed_quantity
            if order.owns_resting_execution_state:
                resting_template_keys.add(key)

        orders = []
        for target in targets:
            target_key = (target.slot_id, target.symbol)
            if target_key in resting_template_keys and target_key not in replacement_keys:
                # A live non-market signal-template order already owns the
                # execution lifecycle for this key. Do not synthesize extra
                # allocator deltas around it until explicit cancel/replace
                # semantics exist.
                continue

            current = self.book.get_position(target.slot_id, target.symbol)
            pending = pending_qty.get(target_key, 0.0)
            current_exposure = current + pending
            delta = target.target_qty - current_exposure

            if abs(delta) < 0.5:   # ignore sub-contract deltas
                continue

            side = "BUY" if delta > 0 else "SELL"
            reduce_only = (
                (current_exposure > 0 and delta < 0 and target.target_qty >= 0)
                or (current_exposure < 0 and delta > 0 and target.target_qty <= 0)
            )
            template = signal_templates.get(target_key)
            order_type = "MARKET"
            limit_price = None
            stop_price = None
            time_in_force = "GTC"
            source = "TARGET_SYNC"
            requested_order_id = None

            requested_intent = self._matching_requested_intent(template, side)
            if requested_intent is not None:
                requested_type = str(requested_intent.order_type or "MARKET").upper()
                if self._requested_intent_has_required_prices(requested_intent, requested_type):
                    order_type = requested_type
                    limit_price = requested_intent.limit_price
                    stop_price = requested_intent.stop_price
                    time_in_force = str(requested_intent.time_in_force or "GTC").upper()
                    source = "SIGNAL_TEMPLATE"
                    requested_order_id = requested_intent.order_id
                    reduce_only = reduce_only or bool(requested_intent.reduce_only)

            orders.append(
                PendingPortfolioOrder(
                    slot_id=target.slot_id,
                    symbol=target.symbol,
                    side=side,
                    quantity=abs(delta),
                    reason=target.reason,
                    order_type=order_type,
                    limit_price=limit_price,
                    stop_price=stop_price,
                    time_in_force=time_in_force,
                    reduce_only=reduce_only,
                    source=source,
                    requested_order_id=requested_order_id,
                )
            )

        return orders

    # ── EOD helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _is_eod_boundary(current_date: date, next_date: Optional[date]) -> bool:
        """
        Returns True if the current bar is the last bar of the trading day.

        Weekend guard: a Friday -> Monday transition (weekday 4 -> 0) is also
        treated as an EOD boundary so positions are never carried into the
        weekend across the gap.

        Args:
            current_date: Calendar date of the current bar.
            next_date: Calendar date of the next bar (None at end of data).

        Returns:
            True if this is the effective end-of-day bar.
        """
        if next_date is None:
            return True
        if next_date != current_date:
            # Any date change counts, including Friday -> Monday gap.
            return True
        return False

    def _liquidate_all_eod(
        self,
        ts: Any,
        price_history: Dict[Tuple[int, str], "pd.Series"],
    ) -> None:
        """
        Force-closes all open positions using each symbol's last-available bar.

        Methodology:
            The union timeline may have a timestamp ts that is NOT present in
            every symbol's DataFrame (gap bars).  Using ts directly would cause
            the price-lookup to silently skip the symbol, leaving the position
            open overnight.  Instead this helper uses self._last_bars — a dict
            kept current by the main loop — which always holds the most recent
            bar that was actually available for each (slot, symbol) pair.

        Args:
            ts: Current union-timeline timestamp (used only as order tag).
            price_history: (slot_id, symbol) -> close price Series for spread computation.
        """
        for (slot_id, symbol), qty in list(self.book.positions.items()):
            if qty == 0:
                continue
            bar = self._last_bars.get((slot_id, symbol))
            if bar is None:
                continue
            side = "SELL" if qty > 0 else "BUY"
            spread_ticks = self._effective_spread_ticks(slot_id, symbol, price_history, ts)
            self._execute_order(
                slot_id, symbol, side, abs(qty), bar,
                execute_at_close=True, reason="EOD_CLOSE",
                effective_spread_ticks=spread_ticks,
            )

    def _is_session_active(
        self,
        timestamp: datetime,
        trade_start_time: Optional[time],
        trade_end_time: Optional[time],
    ) -> bool:
        """
        Returns True if new strategy signals are allowed at this timestamp.
        """
        return is_session_active(
            timestamp=timestamp,
            use_trading_hours=self.settings.use_trading_hours,
            trade_start_time=trade_start_time,
            trade_end_time=trade_end_time,
        )

    def _should_force_eod_close(
        self,
        timestamp: datetime,
        current_date: date,
        eod_close_time: Optional[time],
    ) -> bool:
        """
        Returns True exactly once per day when EOD close time is reached.
        """
        if eod_close_time is None:
            return False
        if current_date in self._eod_closed_dates:
            return False
        return timestamp.time() >= eod_close_time

    @staticmethod
    def _next_eligible_timestamp(
        timestamps: pd.DatetimeIndex,
        index: int,
    ) -> Optional[object]:
        """
        Returns the next union-timeline timestamp, if any.
        """
        if index + 1 >= len(timestamps):
            return None
        return timestamps[index + 1]

    def _effective_pending_quantity(self, order: PendingPortfolioOrder) -> float:
        """
        Returns the executable quantity after applying reduce-only rules.
        """
        requested = float(abs(order.quantity))
        if requested <= 0:
            return 0.0
        if not order.reduce_only:
            return requested

        current_qty = float(self.book.get_position(order.slot_id, order.symbol))
        if order.side == "BUY":
            if current_qty >= 0:
                return 0.0
            return min(requested, abs(current_qty))
        if order.side == "SELL":
            if current_qty <= 0:
                return 0.0
            return min(requested, abs(current_qty))
        return 0.0

    @staticmethod
    def _is_fresh_current_bar_order(
        order: PendingPortfolioOrder,
        timestamp: object,
    ) -> bool:
        """
        Returns True when the order was queued on the same bar as the EOD check.
        """
        if order.placed_at is None:
            return False
        return pd.Timestamp(order.placed_at) == pd.Timestamp(timestamp)

    @staticmethod
    def _is_eod_eligible_pending_order(
        order: PendingPortfolioOrder,
        timestamp: object,
    ) -> bool:
        """
        Returns True when a pending order existed before this bar and is already
        eligible to execute.
        """
        if PortfolioBacktestEngine._is_fresh_current_bar_order(order, timestamp):
            return False
        if order.eligible_from is None:
            return True
        return pd.Timestamp(timestamp) >= pd.Timestamp(order.eligible_from)

    @staticmethod
    def _signal_requested_orders(
        template: Optional[StrategySignal],
    ) -> Tuple[RequestedOrderIntent, ...]:
        """
        Returns the full raw order set preserved on a strategy signal.
        """
        if template is None:
            return ()
        if template.requested_orders:
            return template.requested_orders
        if template.requested_order_id is None and template.requested_order_type is None:
            return ()
        return (
            RequestedOrderIntent(
                order_id=str(template.requested_order_id or ""),
                side=str(template.requested_side or "").upper(),
                quantity=float(template.requested_quantity or 0.0),
                order_type=str(template.requested_order_type or "MARKET").upper(),
                reason=template.reason,
                limit_price=template.requested_limit_price,
                stop_price=template.requested_stop_price,
                time_in_force=str(template.requested_time_in_force or "GTC").upper(),
                reduce_only=bool(template.requested_reduce_only),
            ),
        )

    def _matching_requested_intent(
        self,
        template: Optional[StrategySignal],
        side: str,
    ) -> Optional[RequestedOrderIntent]:
        """
        Returns the raw requested order that should template the normal delta.

        Methodology:
            The portfolio path stays target-driven, so only the requested order
            whose side matches the computed delta is allowed to template that
            delta. This lets the engine ignore sibling protective exits when a
            strategy emits both an entry and a bracket on the same bar.
        """
        for intent in self._signal_requested_orders(template):
            if str(intent.side).upper() == side:
                return intent
        return None

    @staticmethod
    def _requested_intent_has_required_prices(
        intent: RequestedOrderIntent,
        order_type: str,
    ) -> bool:
        """
        Validates minimum price metadata before a requested intent becomes real.
        """
        if order_type == "LIMIT":
            return intent.limit_price is not None
        if order_type == "STOP":
            return intent.stop_price is not None
        if order_type == "STOP_LIMIT":
            return intent.limit_price is not None and intent.stop_price is not None
        return order_type == "MARKET"

    def _replacement_keys(
        self,
        pending_orders: List[PendingPortfolioOrder],
        signal_templates: Dict[Tuple[int, str], StrategySignal],
    ) -> set[Tuple[int, str]]:
        """
        Returns keys whose live resting signal-template orders must be replaced.
        """
        active_resting_keys = {
            (order.slot_id, order.symbol)
            for order in pending_orders
            if order.owns_resting_execution_state
        }
        return {
            key
            for key in signal_templates
            if key in active_resting_keys
        }

    def _build_protective_orders(
        self,
        signal_templates: Dict[Tuple[int, str], StrategySignal],
    ) -> List[PendingPortfolioOrder]:
        """
        Builds standalone protective stop/target orders for already-open positions.

        Methodology:
            Phase 9 still avoids pending-entry child-order semantics. Protective
            siblings are only created when a real portfolio position already
            exists, and their quantity is pinned to the current open exposure so
            reduce-only semantics are enforced by the OMS before execution.
        """
        protective_orders: List[PendingPortfolioOrder] = []

        for key, template in signal_templates.items():
            slot_id, symbol = key
            current_qty = float(self.book.get_position(slot_id, symbol))
            if abs(current_qty) < 0.5:
                continue

            protective_side = "SELL" if current_qty > 0 else "BUY"
            for intent in self._signal_requested_orders(template):
                order_type = str(intent.order_type).upper()
                if not intent.reduce_only or order_type == "MARKET":
                    continue
                if str(intent.side).upper() != protective_side:
                    continue
                if not self._requested_intent_has_required_prices(intent, order_type):
                    continue

                protective_orders.append(
                    PendingPortfolioOrder(
                        slot_id=slot_id,
                        symbol=symbol,
                        side=protective_side,
                        quantity=abs(current_qty),
                        reason=intent.reason,
                        order_type=order_type,
                        limit_price=intent.limit_price,
                        stop_price=intent.stop_price,
                        time_in_force=str(intent.time_in_force).upper(),
                        reduce_only=True,
                        source="SIGNAL_TEMPLATE",
                        requested_order_id=intent.order_id,
                        oco_group_id=intent.oco_group_id,
                        oco_role=intent.oco_role,
                    )
                )

        return protective_orders

    @staticmethod
    def _oco_role(order: PendingPortfolioOrder) -> str:
        """
        Returns the coarse protective role for an OCO-managed pending order.
        """
        if order.oco_role is not None:
            return str(order.oco_role).upper()
        if str(order.order_type).upper() in {"STOP", "STOP_LIMIT"}:
            return "STOP"
        return "TARGET"

    def _preview_pending_fill_price(
        self,
        order: PendingPortfolioOrder,
        bar: pd.Series,
    ) -> Optional[float]:
        """
        Returns the deterministic pre-slippage fill price without mutating state.
        """
        temp_order = Order(
            symbol=order.symbol,
            quantity=abs(order.quantity),
            side=order.side,
            order_type=order.order_type,
            reason=order.reason,
            timestamp=bar.name if hasattr(bar, "name") else None,
            reduce_only=order.reduce_only,
            limit_price=order.limit_price,
            stop_price=order.stop_price,
            time_in_force=order.time_in_force,
        )
        order_type = str(temp_order.order_type).upper()
        handler = self._execution_handlers[order.slot_id]
        if not handler._validate_order(temp_order, order_type):
            return None
        return handler._resolve_bar_fill_price(
            order=temp_order,
            order_type=order_type,
            data_bar=bar,
            execute_at_close=False,
        )

    def _intrabar_replay_slice(
        self,
        slot_id: int,
        symbol: str,
        timestamp: object,
    ) -> Optional[pd.DataFrame]:
        """
        Returns the lower-timeframe slice covering one coarse bar, if complete.
        """
        if not self._intrabar_conflict_replay_enabled():
            return None

        lower_df = self._get_intrabar_conflict_data(slot_id=slot_id, symbol=symbol)
        coarse_df = self._data_map.get((slot_id, symbol))
        if lower_df is None or lower_df.empty or coarse_df is None or timestamp not in coarse_df.index:
            return None

        loc = coarse_df.index.get_loc(timestamp)
        if not isinstance(loc, int) or loc <= 0:
            return None

        start_ts = coarse_df.index[loc - 1]
        end_ts = pd.Timestamp(timestamp)
        replay_step = self._intrabar_resolution_step()
        if replay_step is None:
            return None
        replay = lower_df.loc[(lower_df.index > start_ts) & (lower_df.index <= end_ts)]
        if replay.empty:
            return None
        expected_index = pd.date_range(
            start=pd.Timestamp(start_ts) + replay_step,
            end=end_ts,
            freq=replay_step,
        )
        if expected_index.empty:
            return None
        if len(replay.index) != len(expected_index):
            return None
        if not replay.index.equals(expected_index):
            return None
        return replay

    def _intrabar_resolution_step(self) -> Optional[pd.Timedelta]:
        """
        Returns the configured lower-timeframe step as a Timedelta.
        """
        timeframe = self.settings.intrabar_resolution_timeframe
        if timeframe is None:
            return None

        timeframe_str = str(timeframe).strip().lower()
        if timeframe_str.endswith("m"):
            try:
                minutes = int(timeframe_str[:-1])
            except ValueError:
                return None
            if minutes <= 0:
                return None
            return pd.Timedelta(minutes=minutes)

        if timeframe_str.endswith("h"):
            try:
                hours = int(timeframe_str[:-1])
            except ValueError:
                return None
            if hours <= 0:
                return None
            return pd.Timedelta(hours=hours)

        return None

    def _resolve_oco_winner_on_bar_sequence(
        self,
        orders: List[PendingPortfolioOrder],
        bars: pd.DataFrame,
    ) -> Optional[PendingPortfolioOrder]:
        """
        Resolves the first determinable OCO winner from a chronological bar replay.

        Methodology:
            Replay proceeds strictly in timestamp order using only bars inside
            the current coarse-bar interval. If ambiguity remains on a replay
            bar, the pessimistic policy still applies locally.
        """
        for _, replay_bar in bars.iterrows():
            fillable = [
                order
                for order in orders
                if self._preview_pending_fill_price(order, replay_bar) is not None
            ]
            if not fillable:
                continue
            if len(fillable) == 1:
                return fillable[0]

            stops = [order for order in fillable if self._oco_role(order) == "STOP"]
            if stops:
                return sorted(stops, key=lambda order: order.id)[0]
            return sorted(fillable, key=lambda order: order.id)[0]

        return None

    def _select_oco_winner(
        self,
        orders: List[PendingPortfolioOrder],
        bar_map: Dict[str, pd.Series],
        timestamp: object,
    ) -> Optional[PendingPortfolioOrder]:
        """
        Selects the deterministic winner inside a same-bar OCO conflict.

        Methodology:
            Until lower-timeframe replay is explicitly wired, the portfolio OMS
            uses the pessimistic policy. If both protective stop and target are
            reachable on the same bar, the stop wins.
        """
        fillable = [
            order
            for order in orders
            if self._preview_pending_fill_price(order, bar_map[order.id]) is not None
        ]
        if not fillable:
            return None
        if len(fillable) == 1:
            return fillable[0]

        replay = self._intrabar_replay_slice(
            slot_id=fillable[0].slot_id,
            symbol=fillable[0].symbol,
            timestamp=timestamp,
        )
        if replay is not None:
            replay_winner = self._resolve_oco_winner_on_bar_sequence(fillable, replay)
            if replay_winner is not None:
                return replay_winner

        stops = [order for order in fillable if self._oco_role(order) == "STOP"]
        if stops:
            return sorted(stops, key=lambda order: order.id)[0]
        return sorted(fillable, key=lambda order: order.id)[0]

    @staticmethod
    def _should_invalidate_target_after_fill(order: PendingPortfolioOrder) -> bool:
        """
        Returns True when a fill should retire the preserved target state.
        """
        return order.source == "SIGNAL_TEMPLATE" and order.reduce_only

    @staticmethod
    def _is_expired_pending_order(
        order: PendingPortfolioOrder,
        timestamp: object,
    ) -> bool:
        """
        Returns True when a DAY order has crossed into a new calendar day.
        """
        if str(order.time_in_force).upper() != "DAY" or order.placed_at is None:
            return False
        return pd.Timestamp(timestamp).date() > pd.Timestamp(order.placed_at).date()

    @staticmethod
    def _invalidate_signal_template_state(
        order: PendingPortfolioOrder,
        current_targets: Dict[Tuple[int, str], TargetPosition],
    ) -> None:
        """
        Drops stale target state after an unfilled signal-template order dies.
        """
        if order.source != "SIGNAL_TEMPLATE":
            return
        current_targets.pop((order.slot_id, order.symbol), None)

    @staticmethod
    def _reset_strategy_runtime_state(runner: StrategyRunner) -> None:
        """
        Resets legacy invested-state flags on all portfolio strategy instances.
        """
        runner.reset_runtime_state()

    # ── Main event loop ────────────────────────────────────────────────────────

    def run(self) -> None:
        """
        Runs the portfolio backtest bar-by-bar on the union timeline.

        No-lookahead enforcement:
            Signals generated at close[t] -> orders filled at open[t+1].
        Gap-bar safety:
            Pending orders for symbols with no bar at ts are carried forward
            to the next available bar — never silently discarded.
        """
        if not self._data_map:
            print("[Portfolio] Loading data...")
            self._load_data()

        specs = {
            symbol: self.settings.get_instrument_spec(symbol)
            for slot in self.config.slots
            for symbol in slot.symbols
        }

        # Build slot-local close series. The same structure is used by both:
        # 1) spread estimation at execution time and 2) per-slot sizing volatility.
        slot_price_history: Dict[Tuple[int, str], pd.Series] = {
            (sid, symbol): df["close"]
            for (sid, symbol), df in self._data_map.items()
        }

        all_timestamps = pd.DatetimeIndex([])
        for df in self._data_map.values():
            all_timestamps = all_timestamps.union(df.index)
        all_timestamps = all_timestamps.sort_values()
        timestamps_arr = all_timestamps.to_pydatetime()
        all_dates      = [ts.date() for ts in timestamps_arr]
        data_len       = len(all_timestamps)

        runner = StrategyRunner(self.config, self._data_map, self.settings)
        self.scheduler.reset()
        self._eod_closed_dates.clear()
        trade_start_time = parse_hhmm(self.settings.trade_start_time, "trade_start_time")
        trade_end_time = parse_hhmm(self.settings.trade_end_time, "trade_end_time")
        eod_close_time = parse_hhmm(self.settings.eod_close_time, "eod_close_time")

        order_book = PortfolioOrderBook()
        current_targets: Dict[Tuple[int, str], TargetPosition] = {}
        self._last_bars: Dict[Tuple[int, str], pd.Series] = {}

        # Snapshot equity for sizing (updated by scheduler gate)
        self._allocation_equity = self.book.total_equity

        print(f"[Portfolio] Starting event loop: {data_len:,} bars")

        for i, ts in enumerate(all_timestamps):
            # Break early only when permanently halted and no pending orders remain
            if self.trading_halted_permanently and not order_book.has_open_orders():
                break

            current_date = all_dates[i]
            ts_dt = pd.Timestamp(ts).to_pydatetime()
            session_ok = self._is_session_active(
                ts_dt,
                trade_start_time=trade_start_time,
                trade_end_time=trade_end_time,
            )

            # ── A. Fill pending orders (carry forward through gap bars) ──────────
            # Spread ticks are computed per symbol from history available at ts.
            still_pending: List[PendingPortfolioOrder] = []
            executable_now: List[Tuple[PendingPortfolioOrder, pd.Series, float]] = []
            for order in order_book.active_orders():
                if self._is_expired_pending_order(order, ts):
                    order.status = "CANCELLED"
                    self._invalidate_signal_template_state(order, current_targets)
                    continue
                if order.eligible_from is not None and ts < order.eligible_from:
                    still_pending.append(order)
                    continue
                df = self._data_map.get((order.slot_id, order.symbol))
                if df is None or ts not in df.index:
                    still_pending.append(order)
                    continue
                if not order.is_priority and not session_ok:
                    still_pending.append(order)
                    continue
                effective_qty = self._effective_pending_quantity(order)
                if effective_qty <= 0:
                    order.status = "CANCELLED"
                    self._invalidate_signal_template_state(order, current_targets)
                    continue
                bar = df.loc[ts]
                self._last_bars[(order.slot_id, order.symbol)] = bar  # keep cache current
                executable_now.append((order, bar, effective_qty))

            grouped_orders: Dict[str, List[Tuple[PendingPortfolioOrder, pd.Series, float]]] = {}
            group_sequence: List[str] = []
            for order, bar, effective_qty in executable_now:
                group_id = order.oco_group_id or order.id
                if group_id not in grouped_orders:
                    grouped_orders[group_id] = []
                    group_sequence.append(group_id)
                grouped_orders[group_id].append((order, bar, effective_qty))

            for group_id in group_sequence:
                group = grouped_orders[group_id]
                if len(group) == 1 or group[0][0].oco_group_id is None:
                    order, bar, effective_qty = group[0]
                    spread_ticks = self._effective_spread_ticks(
                        order.slot_id, order.symbol, slot_price_history, ts
                    )
                    if order.status == "SUBMITTED":
                        order.status = "ACCEPTED"
                    executed = self._execute_order(
                        order.slot_id, order.symbol, order.side, effective_qty, bar,
                        reason=order.reason,
                        effective_spread_ticks=spread_ticks,
                        reduce_only=order.reduce_only,
                        order_type=order.order_type,
                        limit_price=order.limit_price,
                        stop_price=order.stop_price,
                        time_in_force=order.time_in_force,
                    )
                    if executed:
                        order.status = "FILLED"
                        if self._should_invalidate_target_after_fill(order):
                            self._invalidate_signal_template_state(order, current_targets)
                    else:
                        if str(order.time_in_force).upper() == "IOC":
                            order.status = "CANCELLED"
                            self._invalidate_signal_template_state(order, current_targets)
                        else:
                            still_pending.append(order)
                    continue

                bar_map = {order.id: bar for order, bar, _ in group}
                candidate_orders = [order for order, _, _ in group]
                winner = self._select_oco_winner(candidate_orders, bar_map, timestamp=ts)
                if winner is None:
                    for order, _, _ in group:
                        if str(order.time_in_force).upper() == "IOC":
                            order.status = "CANCELLED"
                            self._invalidate_signal_template_state(order, current_targets)
                        else:
                            still_pending.append(order)
                    continue

                winner_bar = bar_map[winner.id]
                winner_qty = next(
                    effective_qty
                    for order, _, effective_qty in group
                    if order.id == winner.id
                )
                spread_ticks = self._effective_spread_ticks(
                    winner.slot_id, winner.symbol, slot_price_history, ts
                )
                if winner.status == "SUBMITTED":
                    winner.status = "ACCEPTED"
                executed = self._execute_order(
                    winner.slot_id, winner.symbol, winner.side, winner_qty, winner_bar,
                    reason=winner.reason,
                    effective_spread_ticks=spread_ticks,
                    reduce_only=winner.reduce_only,
                    order_type=winner.order_type,
                    limit_price=winner.limit_price,
                    stop_price=winner.stop_price,
                    time_in_force=winner.time_in_force,
                )
                if executed:
                    winner.status = "FILLED"
                    self._invalidate_signal_template_state(winner, current_targets)
                    for sibling, _, _ in group:
                        if sibling.id == winner.id:
                            continue
                        sibling.status = "CANCELLED"
                        self._invalidate_signal_template_state(sibling, current_targets)
                else:
                    if str(winner.time_in_force).upper() == "IOC":
                        winner.status = "CANCELLED"
                        self._invalidate_signal_template_state(winner, current_targets)
                    else:
                        still_pending.append(winner)
                    for sibling, _, _ in group:
                        if sibling.id != winner.id:
                            still_pending.append(sibling)
            order_book.replace_active_orders(still_pending)

            # ── B. Mark-to-market ────────────────────────────────────────────────
            prices = {
                (sid, symbol): self._data_map[(sid, symbol)].loc[ts, "close"]
                for (sid, symbol), df in self._data_map.items()
                if ts in df.index
            }
            # Update last-bar cache with any symbol that has a bar at ts
            for (sid, symbol), df in self._data_map.items():
                if ts in df.index:
                    self._last_bars[(sid, symbol)] = df.loc[ts]
            self.book.mark_to_market(prices, specs)

            # ── C. Risk-limit check ──────────────────────────────────────────────
            self._check_risk_limits(current_date)

            # ── D. Halt handling: liquidate and skip strategy logic ───────────────
            if self.trading_halted_today or self.trading_halted_permanently:
                order_book.cancel_where(lambda order: not order.is_priority)
                current_targets.clear()
                for (slot_id, symbol), qty in list(self.book.positions.items()):
                    if qty != 0:
                        df = self._data_map.get((slot_id, symbol))
                        if df is not None and ts in df.index:
                            bar = df.loc[ts]
                            spread_ticks = self._effective_spread_ticks(
                                slot_id, symbol, slot_price_history, ts
                            )
                            self._liquidate_slot(
                                slot_id, symbol, qty, bar,
                                reason="RISK_LIQ",
                                effective_spread_ticks=spread_ticks,
                            )
                self._reset_strategy_runtime_state(runner)
                self.book.mark_to_market(prices, specs)
                self.book.record_snapshot(ts, instrument_specs=specs)
                continue

            # ── E. Scheduler gate: snapshot equity for sizing ────────────────────
            if self.scheduler.should_rebalance(ts):
                self._allocation_equity = self.book.total_equity

            # ── F. Collect intraday signals ──────────────────────────────────────
            bar_map: Dict[Tuple[int, str], pd.Series] = {
                (sid, sym): df.loc[ts]
                for (sid, sym), df in self._data_map.items()
                if ts in df.index
            }
            signals = (
                runner.collect_signals(
                    bar_map,
                    ts,
                    current_positions=dict(self.book.positions),
                )
                if session_ok
                else []
            )
            signal_templates = {
                (signal.slot_id, signal.symbol): signal
                for signal in signals
            }
            replacement_keys = self._replacement_keys(
                order_book.active_orders(),
                signal_templates,
            )

            # ── G. Compute target positions via vol-targeting ────────────────────
            if signals:
                # Build a truncated price history up to and including bar[t]
                # so the vol estimate never looks ahead.
                history_to_t: Dict[Tuple[int, str], pd.Series] = {
                    key: series.loc[:ts]
                    for key, series in slot_price_history.items()
                }
                # Allocator.compute_targets expects current_prices keyed by symbol
                # (str), not by (slot_id, symbol) tuple used by mark_to_market.
                # Flatten here; all slots share the same instrument price.
                symbol_prices: Dict[str, float] = {
                    sym: p for (_, sym), p in prices.items()
                }
                new_targets = self.allocator.compute_targets(
                    signals,
                    self._allocation_equity,
                    symbol_prices,
                    specs,
                    history_to_t,
                    bars_per_year=self._bars_per_year,
                )
                for t in new_targets:
                    current_targets[(t.slot_id, t.symbol)] = t

            # Build full target list from maintained state
            target_list = list(current_targets.values())

            # ── H. Compute order deltas -> queue for t+1 ─────────────────────────
            orders = self._compute_orders(
                target_list,
                order_book.active_orders(),
                signal_templates=signal_templates,
                replacement_keys=replacement_keys,
            )
            orders.extend(self._build_protective_orders(signal_templates))
            next_eligible_ts = self._next_eligible_timestamp(all_timestamps, i)
            if replacement_keys:
                order_book.cancel_where(
                    lambda order: (
                        (order.slot_id, order.symbol) in replacement_keys
                        and order.owns_resting_execution_state
                    )
                )
            order_book.submit_many(orders, placed_at=ts, eligible_from=next_eligible_ts)

            # ── I. Time-based forced EOD close ────────────────────────────────────
            if self._should_force_eod_close(ts_dt, current_date, eod_close_time):
                # 1. Execute only already-pending market orders at market-on-close.
                #    Fresh bar[t] orders are cancelled so the t+1 contract holds.
                for order in order_book.pull_all():
                    if not self._is_eod_eligible_pending_order(order, ts):
                        order.status = "CANCELLED"
                        self._invalidate_signal_template_state(order, current_targets)
                        continue
                    if order.order_type != "MARKET":
                        order.status = "CANCELLED"
                        self._invalidate_signal_template_state(order, current_targets)
                        continue
                    bar = self._last_bars.get((order.slot_id, order.symbol))
                    if bar is not None:
                        effective_qty = self._effective_pending_quantity(order)
                        if effective_qty <= 0:
                            order.status = "CANCELLED"
                            self._invalidate_signal_template_state(order, current_targets)
                            continue
                        spread_ticks = self._effective_spread_ticks(
                            order.slot_id, order.symbol, slot_price_history, ts
                        )
                        executed = self._execute_order(
                            order.slot_id, order.symbol, order.side, effective_qty, bar,
                            execute_at_close=True, reason=order.reason,
                            effective_spread_ticks=spread_ticks,
                            reduce_only=order.reduce_only,
                            order_type=order.order_type,
                            limit_price=order.limit_price,
                            stop_price=order.stop_price,
                            time_in_force=order.time_in_force,
                        )
                        if executed:
                            order.status = "FILLED"
                        else:
                            order.status = "CANCELLED"
                            self._invalidate_signal_template_state(order, current_targets)
                    else:
                        order.status = "CANCELLED"
                        self._invalidate_signal_template_state(order, current_targets)
                order_book.replace_active_orders([])

                # 2. Force-liquidate ALL open positions using last-available bar
                #    (not ts — prevents silent skip on gap-bar symbols)
                self._liquidate_all_eod(ts, slot_price_history)

                # 3. Re-mark after all closings
                self.book.mark_to_market(prices, specs)

                # 4. Clear targets so allocator does not reopen at bar[t+1] open
                current_targets.clear()

                # 5. Reset strategy invested-state flags
                self._reset_strategy_runtime_state(runner)
                self._eod_closed_dates.add(current_date)

            # ── J. Snapshot ───────────────────────────────────────────────────────
            self.book.record_snapshot(ts, instrument_specs=specs)

        print("[Portfolio] Backtest complete.")

    # ── Results ────────────────────────────────────────────────────────────────

    def show_results(
        self,
        benchmark: Optional[pd.DataFrame] = None,
        output_dir: Optional[Path] = None,
        manifest_metadata: Optional[Dict[str, object]] = None,
    ) -> None:
        """
        Computes metrics, prints the full report, and saves all result artifacts.

        Args:
            benchmark: Optional DataFrame with 'close' column for buy-and-hold comparison.
            output_dir: Optional alternate artifact directory for scenario runs.
            manifest_metadata: Optional extra metadata persisted into manifest.json.
        """
        from src.backtest_engine.analytics import PerformanceMetrics

        history = self.book.get_history_df()
        if history.empty:
            print("[Portfolio] No history to display.")
            return

        all_trades = [t for trades in self._slot_trades.values() for t in trades]

        analytics = PerformanceMetrics(risk_free_rate=self.settings.risk_free_rate)
        metrics   = analytics.calculate_metrics(history, all_trades)
        report    = analytics.get_full_report_str(metrics, all_trades)
        print(report)

        save_portfolio_results(
            history=history,
            exposure_df=self.book.get_exposure_df(),
            slot_trades=self._slot_trades,
            report_str=report,
            metrics=metrics,
            slot_names={
                i: f"{slot.strategy_class.__name__}({'_'.join(slot.symbols)}+{slot.timeframe.upper()})"
                for i, slot in enumerate(self.config.slots)
            },
            benchmark=benchmark,
            data_map=self._data_map,
            slot_weights={
                i: slot.weight for i, slot in enumerate(self.config.slots)
            },
            instrument_specs=self.settings.instrument_specs,
            output_dir=output_dir,
            manifest_metadata=manifest_metadata,
        )
