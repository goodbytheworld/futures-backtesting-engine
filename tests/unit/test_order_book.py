from __future__ import annotations

from datetime import date

from src.backtest_engine.execution import Order
from src.backtest_engine.execution.order_book import OrderBook


def test_submit_marks_order_submitted_and_stamps_timestamp() -> None:
    """Submitted orders must receive placement metadata in the order book."""
    book = OrderBook()
    order = Order(symbol="ES", quantity=1, side="BUY")

    book.submit(order, placed_at=date(2025, 1, 1))

    assert book.has_open_orders()
    assert order.status == "SUBMITTED"
    assert order.placed_at == date(2025, 1, 1)


def test_process_active_orders_retains_unfilled_resting_order() -> None:
    """Unfilled non-terminal orders must remain active across bars."""
    book = OrderBook()
    order = Order(symbol="ES", quantity=1, side="BUY", order_type="LIMIT", limit_price=100.0, time_in_force="GTC")
    book.submit(order, placed_at=date(2025, 1, 1))

    fills = book.process_active_orders(
        attempt_fill=lambda _: None,
        can_attempt=lambda _: True,
    )

    assert fills == []
    assert book.has_open_orders()
    assert book.active_orders()[0].id == order.id


def test_cancel_expired_day_orders_removes_previous_day_orders() -> None:
    """DAY orders must expire when the engine moves into a later date."""
    book = OrderBook()
    day_order = Order(symbol="ES", quantity=1, side="BUY", order_type="LIMIT", limit_price=100.0, time_in_force="DAY")
    gtc_order = Order(symbol="ES", quantity=1, side="BUY", order_type="LIMIT", limit_price=99.0, time_in_force="GTC")
    book.submit(day_order, placed_at=date(2025, 1, 1))
    book.submit(gtc_order, placed_at=date(2025, 1, 1))

    cancelled = book.cancel_expired_day_orders(current_date=date(2025, 1, 2))

    assert len(cancelled) == 1
    assert cancelled[0].id == day_order.id
    assert cancelled[0].status == "CANCELLED"
    assert len(book.active_orders()) == 1
    assert book.active_orders()[0].id == gtc_order.id
