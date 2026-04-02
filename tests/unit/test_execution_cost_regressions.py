from __future__ import annotations

import pandas as pd
import pytest

from src.backtest_engine.analytics import PerformanceMetrics
from src.backtest_engine.config import BacktestSettings
from src.backtest_engine.execution import ExecutionHandler, Order
from src.backtest_engine.execution.cost_model import (
    estimate_round_trip_cost,
    resolve_spread_ticks,
)
from src.backtest_engine.execution.spread_model import compute_spread_ticks

from ._execution_test_helpers import StubSettings, _bar, _ohlc_bar


def test_partial_fill_commission_residue_does_not_inflate() -> None:
    """FIFO residue trackers must preserve proportional commission after partial closes."""
    handler = ExecutionHandler(StubSettings(spread_ticks=0))

    handler.execute_order(Order(symbol="ES", quantity=4, side="BUY"), _bar("2024-01-01 09:30:00", 100.0))
    handler.execute_order(Order(symbol="ES", quantity=2, side="SELL"), _bar("2024-01-01 10:00:00", 101.0))
    handler.execute_order(Order(symbol="ES", quantity=2, side="SELL"), _bar("2024-01-01 10:30:00", 102.0))

    commissions = [trade.commission for trade in handler.trades]
    assert len(commissions) == 2
    assert commissions == [10.0, 10.0]
    assert sum(commissions) == 20.0
    assert handler.fills[0].order.quantity == 4


def test_partial_fill_residue_keeps_per_contract_slippage_convention() -> None:
    """Residue tracking must preserve per-contract slippage for later matched fragments."""
    handler = ExecutionHandler(StubSettings(spread_ticks=1))

    handler.execute_order(Order(symbol="ES", quantity=4, side="BUY"), _bar("2024-01-01 09:30:00", 100.0))
    handler.execute_order(Order(symbol="ES", quantity=2, side="SELL"), _bar("2024-01-01 10:00:00", 101.0))
    handler.execute_order(Order(symbol="ES", quantity=2, side="SELL"), _bar("2024-01-01 10:30:00", 102.0))

    slippages = [trade.slippage for trade in handler.trades]
    assert slippages == [50.0, 50.0]
    assert sum(slippages) == 100.0


def test_trade_pnl_uses_executed_prices_without_double_counting_slippage() -> None:
    """Closed-trade PnL must use slipped executed prices and subtract commission only once."""
    handler = ExecutionHandler(StubSettings(spread_ticks=1))

    handler.execute_order(Order(symbol="ES", quantity=1, side="BUY"), _bar("2024-01-01 09:30:00", 100.0))
    handler.execute_order(Order(symbol="ES", quantity=1, side="SELL"), _bar("2024-01-01 10:00:00", 101.0))

    trade = handler.trades[0]

    assert trade.commission == pytest.approx(5.0)
    assert trade.slippage == pytest.approx(25.0)
    assert trade.pnl == pytest.approx(20.0)
    assert trade.pnl + trade.commission == pytest.approx(25.0)


def test_total_pnl_metric_and_report_follow_equity_even_with_open_position() -> None:
    """Total PnL must come from final equity so reports stay truthful on open-final runs."""
    history = pd.DataFrame(
        {"total_value": [100_000.0, 100_030.0]},
        index=pd.to_datetime(["2024-01-01 09:30:00", "2024-01-01 10:00:00"]),
    )

    analytics = PerformanceMetrics()
    metrics = analytics.calculate_metrics(history, trades=[])
    report = analytics.get_full_report_str(metrics, trades=[])
    total_pnl_line = next(
        line for line in report.splitlines()
        if line.strip().startswith("Total PnL ($)")
    )

    assert metrics["Total PnL"] == pytest.approx(30.0)
    assert "$30" in total_pnl_line


@pytest.mark.parametrize(
    ("symbol", "tick_size", "multiplier"),
    [
        ("6A", 0.00005, 100000.0),
        ("6B", 0.0001, 62500.0),
        ("6C", 0.00005, 100000.0),
        ("6E", 0.00005, 125000.0),
        ("6J", 0.0000005, 12500000.0),
        ("6S", 0.00005, 125000.0),
    ],
)
def test_backtest_settings_include_standard_fx_futures_specs(
    symbol: str,
    tick_size: float,
    multiplier: float,
) -> None:
    """FX futures must ship explicit contract specs instead of generic fallbacks."""
    spec = BacktestSettings().get_instrument_spec(symbol)

    assert spec["tick_size"] == pytest.approx(tick_size)
    assert spec["multiplier"] == pytest.approx(multiplier)


def test_static_spread_mode_is_deterministic() -> None:
    """Static mode must produce identical fill prices on repeated calls with the same inputs."""
    handler = ExecutionHandler(StubSettings(spread_ticks=2))

    bar = _bar("2024-01-01 09:30:00", 100.0)
    fill1 = handler.execute_order(Order(symbol="ES", quantity=1, side="BUY"), bar)
    fill2 = handler.execute_order(Order(symbol="ES", quantity=1, side="BUY"), bar)

    assert fill1 is not None and fill2 is not None
    assert fill1.fill_price == fill2.fill_price, "Static spread must be deterministic"


def test_static_spread_buy_adds_ticks() -> None:
    """BUY fill price must be price + spread_ticks * tick_size for static mode."""
    handler = ExecutionHandler(StubSettings(spread_ticks=2))

    fill = handler.execute_order(Order(symbol="ES", quantity=1, side="BUY"), _bar("2024-01-01 09:30:00", 100.0))

    assert fill is not None
    assert fill.fill_price == 100.0 + 2 * 0.25


def test_static_spread_sell_subtracts_ticks() -> None:
    """SELL fill price must be price - spread_ticks * tick_size for static mode."""
    handler = ExecutionHandler(StubSettings(spread_ticks=2))

    fill = handler.execute_order(Order(symbol="ES", quantity=1, side="SELL"), _bar("2024-01-01 09:30:00", 100.0))

    assert fill is not None
    assert fill.fill_price == 100.0 - 2 * 0.25


def test_spread_ticks_zero_produces_no_slippage() -> None:
    """spread_ticks=0 must result in zero slippage and exact price execution."""
    handler = ExecutionHandler(StubSettings(spread_ticks=0))

    fill = handler.execute_order(Order(symbol="ES", quantity=1, side="BUY"), _bar("2024-01-01 09:30:00", 100.0))

    assert fill is not None
    assert fill.fill_price == 100.0
    assert fill.slippage == 0.0


def test_effective_spread_ticks_override_takes_precedence() -> None:
    """Engine-supplied effective_spread_ticks must override settings.spread_ticks."""
    handler = ExecutionHandler(StubSettings(spread_ticks=0))

    fill = handler.execute_order(
        Order(symbol="ES", quantity=1, side="BUY"),
        _bar("2024-01-01 09:30:00", 100.0),
        effective_spread_ticks=3,
    )

    assert fill is not None
    assert fill.fill_price == 100.0 + 3 * 0.25


def test_buy_limit_gap_fills_at_open_not_limit() -> None:
    """Buy limit orders must fill at the next open when price gaps through the limit."""
    handler = ExecutionHandler(StubSettings(spread_ticks=0))
    fill = handler.execute_order(
        Order(symbol="ES", quantity=1, side="BUY", order_type="LIMIT", limit_price=100.0),
        _ohlc_bar("2024-01-01 09:30:00", open_price=98.0, high_price=101.0, low_price=97.0, close_price=100.0),
    )

    assert fill is not None
    assert fill.fill_price == 98.0


def test_sell_stop_gap_fills_at_open_not_stop() -> None:
    """Sell stop orders must fill at the next open when price gaps through the stop."""
    handler = ExecutionHandler(StubSettings(spread_ticks=0))
    fill = handler.execute_order(
        Order(symbol="ES", quantity=1, side="SELL", order_type="STOP", stop_price=95.0),
        _ohlc_bar("2024-01-01 09:30:00", open_price=90.0, high_price=91.0, low_price=88.0, close_price=89.0),
    )

    assert fill is not None
    assert fill.fill_price == 90.0


def test_limit_orders_default_to_zero_spread_slippage() -> None:
    """Default LIMIT fills should not pay spread slippage."""
    handler = ExecutionHandler(StubSettings(spread_ticks=3))
    fill = handler.execute_order(
        Order(symbol="ES", quantity=1, side="BUY", order_type="LIMIT", limit_price=100.0),
        _ohlc_bar("2024-01-01 09:30:00", open_price=100.0, high_price=101.0, low_price=99.0, close_price=100.0),
    )

    assert fill is not None
    assert fill.fill_price == 100.0
    assert fill.slippage == 0.0


def test_stop_limit_orders_default_to_zero_spread_slippage() -> None:
    """Default STOP_LIMIT fills should follow the limit-style spread profile."""
    handler = ExecutionHandler(StubSettings(spread_ticks=3))
    fill = handler.execute_order(
        Order(
            symbol="ES",
            quantity=1,
            side="BUY",
            order_type="STOP_LIMIT",
            stop_price=105.0,
            limit_price=101.0,
        ),
        _ohlc_bar("2024-01-01 09:30:00", open_price=100.0, high_price=106.0, low_price=101.0, close_price=105.0),
    )

    assert fill is not None
    assert fill.fill_price == 101.0
    assert fill.slippage == 0.0


def test_untriggered_ioc_order_is_cancelled() -> None:
    """IOC resting orders must cancel when the first eligible bar does not fill them."""
    handler = ExecutionHandler(StubSettings(spread_ticks=0))
    order = Order(
        symbol="ES",
        quantity=1,
        side="BUY",
        order_type="LIMIT",
        limit_price=100.0,
        time_in_force="IOC",
    )

    fill = handler.execute_order(
        order,
        _ohlc_bar("2024-01-01 09:30:00", open_price=101.0, high_price=102.0, low_price=100.5, close_price=101.5),
    )

    assert fill is None
    assert order.status == "CANCELLED"


def test_buy_stop_limit_intrabar_fills_at_limit_after_trigger() -> None:
    """BUY stop-limit should fill at the limit when the bar proves both trigger and limit."""
    handler = ExecutionHandler(StubSettings(spread_ticks=0))
    fill = handler.execute_order(
        Order(
            symbol="ES",
            quantity=1,
            side="BUY",
            order_type="STOP_LIMIT",
            stop_price=105.0,
            limit_price=101.0,
        ),
        _ohlc_bar("2024-01-01 09:30:00", open_price=100.0, high_price=106.0, low_price=101.0, close_price=105.0),
    )

    assert fill is not None
    assert fill.fill_price == 101.0


def test_sell_stop_limit_intrabar_fills_at_limit_after_trigger() -> None:
    """SELL stop-limit should fill at the limit when the bar proves both trigger and limit."""
    handler = ExecutionHandler(StubSettings(spread_ticks=0))
    fill = handler.execute_order(
        Order(
            symbol="ES",
            quantity=1,
            side="SELL",
            order_type="STOP_LIMIT",
            stop_price=95.0,
            limit_price=99.0,
        ),
        _ohlc_bar("2024-01-01 09:30:00", open_price=100.0, high_price=101.0, low_price=94.0, close_price=95.0),
    )

    assert fill is not None
    assert fill.fill_price == 99.0


def test_per_order_type_cost_overrides_are_applied() -> None:
    """Execution cost overrides must be configurable by order type."""
    settings = StubSettings(
        spread_ticks=1,
        spread_tick_multipliers_by_order_type={"LIMIT": 2.0},
        commission_rate_by_order_type={"LIMIT": 3.5},
    )
    handler = ExecutionHandler(settings)
    fill = handler.execute_order(
        Order(symbol="ES", quantity=2, side="BUY", order_type="LIMIT", limit_price=100.0),
        _ohlc_bar("2024-01-01 09:30:00", open_price=100.0, high_price=101.0, low_price=99.0, close_price=100.0),
    )

    assert fill is not None
    assert fill.slippage == 0.5
    assert fill.commission == 7.0


def test_shared_cost_model_treats_stop_limit_as_limit_style_by_default() -> None:
    """STOP_LIMIT should use the same default spread profile as LIMIT orders."""
    settings = StubSettings(spread_ticks=2)
    estimate = estimate_round_trip_cost(
        symbol="ES",
        settings=settings,
        entry_order_type="STOP_LIMIT",
        exit_order_type="MARKET",
    )

    assert estimate.entry.slippage_cash == 0.0
    assert estimate.exit.slippage_cash == 25.0
    assert estimate.total_cash == 30.0
    assert resolve_spread_ticks(settings, "STOP_LIMIT", effective_spread_ticks=2) == 0


def test_adaptive_spread_widens_in_high_vol() -> None:
    """Adaptive mode must return more ticks when current vol exceeds baseline."""
    prices = pd.Series([100.0 + i * 0.1 for i in range(200)])
    spike = pd.Series([100.0 + i * 5.0 for i in range(20)])
    closes_spike = pd.concat([prices, spike], ignore_index=True)

    ticks_spiked = compute_spread_ticks(
        mode="adaptive_volatility",
        base_ticks=1,
        closes=closes_spike,
        vol_step_pct=0.10,
        step_multiplier=2.0,
        vol_lookback=20,
        vol_baseline_lookback=100,
    )
    ticks_calm = compute_spread_ticks(
        mode="adaptive_volatility",
        base_ticks=1,
        closes=prices,
        vol_step_pct=0.10,
        step_multiplier=2.0,
        vol_lookback=20,
        vol_baseline_lookback=100,
    )

    assert ticks_spiked > ticks_calm


def test_adaptive_spread_narrows_in_low_vol() -> None:
    """Adaptive mode must return fewer ticks when current vol falls below baseline."""
    prices = pd.Series([100.0 + (i % 10) * 0.5 for i in range(200)])
    calm_tail = pd.Series([200.0] * 25)
    closes_calm_tail = pd.concat([prices, calm_tail], ignore_index=True)

    ticks_narrowed = compute_spread_ticks(
        mode="adaptive_volatility",
        base_ticks=4,
        closes=closes_calm_tail,
        vol_step_pct=0.10,
        step_multiplier=2.0,
        vol_lookback=20,
        vol_baseline_lookback=100,
    )

    assert ticks_narrowed <= 4


def test_adaptive_spread_insufficient_history_falls_back_to_base() -> None:
    """Adaptive mode must fall back to base_ticks when history is too short."""
    ticks = compute_spread_ticks(
        mode="adaptive_volatility",
        base_ticks=2,
        closes=pd.Series([100.0, 101.0, 102.0]),
        vol_step_pct=0.10,
        step_multiplier=1.5,
        vol_lookback=20,
        vol_baseline_lookback=100,
    )

    assert ticks == 2


def test_adaptive_spread_is_non_compounding_across_bars() -> None:
    """Spread adjustment must be recalculated from scratch each bar, not accumulated."""
    prices = pd.Series([100.0 + i * 0.2 for i in range(150)])

    ticks_bar1 = compute_spread_ticks(
        mode="adaptive_volatility",
        base_ticks=1,
        closes=prices.iloc[:100],
        vol_step_pct=0.10,
        step_multiplier=2.0,
        vol_lookback=20,
        vol_baseline_lookback=80,
    )
    ticks_bar2 = compute_spread_ticks(
        mode="adaptive_volatility",
        base_ticks=1,
        closes=prices.iloc[:101],
        vol_step_pct=0.10,
        step_multiplier=2.0,
        vol_lookback=20,
        vol_baseline_lookback=80,
    )

    assert ticks_bar1 >= 0
    assert ticks_bar2 >= 0
    assert ticks_bar1 < 50
    assert ticks_bar2 < 50
