"""Tests for the portfolio market-only order book."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from src.backtest_engine.portfolio_layer.domain.orders import PendingPortfolioOrder
from src.backtest_engine.portfolio_layer.execution.order_book import PortfolioOrderBook


def test_portfolio_order_book_submit_sets_status_and_timestamps() -> None:
    """Submitting a portfolio order must stamp placement metadata."""
    book = PortfolioOrderBook()
    placed_at = datetime(2025, 1, 1, 9, 30)
    eligible_from = datetime(2025, 1, 1, 10, 0)
    order = PendingPortfolioOrder(
        slot_id=0,
        symbol="ES",
        side="BUY",
        quantity=1.0,
    )

    book.submit(order, placed_at=placed_at, eligible_from=eligible_from)

    assert book.has_open_orders()
    assert order.status == "SUBMITTED"
    assert order.placed_at == placed_at
    assert order.eligible_from == eligible_from


def test_portfolio_order_book_cancel_where_removes_matching_orders() -> None:
    """Cancelling matching orders must leave only the non-matching active set."""
    book = PortfolioOrderBook()
    buy_order = PendingPortfolioOrder(slot_id=0, symbol="ES", side="BUY", quantity=1.0)
    sell_order = PendingPortfolioOrder(slot_id=0, symbol="ES", side="SELL", quantity=1.0)
    book.submit_many([buy_order, sell_order], placed_at=datetime(2025, 1, 1, 9, 30))

    cancelled = book.cancel_where(lambda order: order.side == "SELL")

    assert len(cancelled) == 1
    assert cancelled[0].id == sell_order.id
    assert cancelled[0].status == "CANCELLED"
    assert len(book.active_orders()) == 1
    assert book.active_orders()[0].id == buy_order.id


def test_portfolio_order_book_cancel_where_cascades_to_attached_children() -> None:
    """Cancelling a parent order must also cancel any attached child descendants."""
    book = PortfolioOrderBook()
    parent = PendingPortfolioOrder(slot_id=0, symbol="ES", side="BUY", quantity=1.0)
    child = PendingPortfolioOrder(
        slot_id=0,
        symbol="ES",
        side="SELL",
        quantity=1.0,
        reduce_only=True,
        parent_order_id=parent.id,
        activation_status="PENDING_PARENT_FILL",
    )
    book.submit_many([parent, child], placed_at=datetime(2025, 1, 1, 9, 30))

    cancelled = book.cancel_where(lambda order: order.id == parent.id)

    assert {order.id for order in cancelled} == {parent.id, child.id}
    assert all(order.status == "CANCELLED" for order in cancelled)
    assert book.active_orders() == []


def test_portfolio_order_book_parent_fill_activates_child_for_same_bar_processing() -> None:
    """A parent fill should arm its child and allow a second same-bar processing pass."""
    book = PortfolioOrderBook()
    parent = PendingPortfolioOrder(slot_id=0, symbol="ES", side="BUY", quantity=1.0)
    child = PendingPortfolioOrder(
        slot_id=0,
        symbol="ES",
        side="SELL",
        quantity=1.0,
        reduce_only=True,
        parent_order_id=parent.id,
        activation_status="PENDING_PARENT_FILL",
        oco_group_id="bracket",
        oco_role="STOP",
    )
    book.submit_many([parent, child], placed_at=datetime(2025, 1, 1, 9, 30))

    attempts: list[str] = []

    def _fill(order: PendingPortfolioOrder):
        attempts.append(order.id)
        order.status = "FILLED"
        phase = "OPEN" if order.id == parent.id else "INTRABAR"
        return SimpleNamespace(
            order=SimpleNamespace(quantity=order.quantity),
            timestamp=datetime(2025, 1, 1, 10, 0),
            fill_phase=phase,
        )

    fills = book.process_active_orders(
        attempt_fill=_fill,
        can_attempt=lambda order: True,
        preview_fill=lambda order: 100.0,
    )

    assert len(fills) == 2
    assert attempts == [parent.id, child.id]
    assert child.activation_status == "ACTIVE"
    assert child.activated_by_fill_phase == "OPEN"
    assert book.active_orders() == []
