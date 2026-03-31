"""Tests for the portfolio market-only order book."""

from __future__ import annotations

from datetime import datetime

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
