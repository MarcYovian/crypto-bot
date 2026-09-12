"""Unit tests for TradeAggregate and TradeStateMachine domain models."""

import pytest
from decimal import Decimal
from datetime import datetime

from src.domain.aggregates.order_aggregate import OrderAggregate
from src.domain.aggregates.trade_aggregate import TradeAggregate
from src.domain.aggregates.trade_state_machine import TradeStateMachine
from src.domain.events.trade_events import (
    StopLossMovedEvent,
    TradeCancelledEvent,
    TradeClosedEvent,
    TradeOpenedEvent,
    TradePartiallyClosedEvent,
    TradeWaitingEntryEvent,
)
from src.domain.exceptions.risk import StopLossCannotExceedEntryError
from src.domain.exceptions.trade import InvalidTradeStateError
from src.domain.value_objects.side import MarginMode, OrderSide
from src.domain.value_objects.trade_status import OrderPurpose, OrderStatus, OrderType, TradeStatus


# =============================================================================
# TRADE STATE MACHINE TESTS
# =============================================================================

def test_trade_state_machine_valid_transitions():
    """Verify allowed state transitions pass validation."""
    assert TradeStateMachine.can_transition(TradeStatus.WAITING_ENTRY, TradeStatus.OPEN) is True
    assert TradeStateMachine.can_transition(TradeStatus.WAITING_ENTRY, TradeStatus.CANCELLED) is True

    assert TradeStateMachine.can_transition(TradeStatus.OPEN, TradeStatus.PARTIAL) is True
    assert TradeStateMachine.can_transition(TradeStatus.OPEN, TradeStatus.CLOSED) is True

    assert TradeStateMachine.can_transition(TradeStatus.PARTIAL, TradeStatus.PARTIAL) is True
    assert TradeStateMachine.can_transition(TradeStatus.PARTIAL, TradeStatus.CLOSED) is True


def test_trade_state_machine_invalid_transitions():
    """Verify disallowed state transitions raise InvalidTradeStateError."""
    assert TradeStateMachine.can_transition(TradeStatus.CLOSED, TradeStatus.OPEN) is False
    assert TradeStateMachine.can_transition(TradeStatus.CANCELLED, TradeStatus.PARTIAL) is False
    assert TradeStateMachine.can_transition(TradeStatus.CLOSED, TradeStatus.CLOSED) is False

    with pytest.raises(InvalidTradeStateError) as exc_info:
        TradeStateMachine.validate_transition(TradeStatus.CLOSED, TradeStatus.OPEN, trade_id=99)
    assert "cannot transition from 'CLOSED' to 'OPEN'" in str(exc_info.value)
    assert exc_info.value.details["current_status"] == "CLOSED"


# =============================================================================
# TRADE AGGREGATE FACTORY & LIFECYCLE TESTS
# =============================================================================

def test_create_pending_trade_aggregate():
    """Verify create_pending factory sets WAITING_ENTRY and records TradeWaitingEntryEvent."""
    agg = TradeAggregate.create_pending(
        account_id=1,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        target_entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        position_size=Decimal("0.5"),
        leverage=10,
        tp_targets=[Decimal("62000.0"), Decimal("64000.0")],
        trade_id=10,
    )

    assert agg.id == 10
    assert agg.status == TradeStatus.WAITING_ENTRY
    assert agg.remaining_qty == Decimal("0.5")
    assert agg.risk_amount == Decimal("1000.0")  # (60000 - 58000) * 0.5
    assert agg.margin_used == Decimal("3000.0")  # (60000 * 0.5) / 10

    events = agg.collect_events()
    assert len(events) == 1
    assert isinstance(events[0], TradeWaitingEntryEvent)
    assert events[0].target_entry_price == Decimal("60000.0")
    assert events[0].tp1_price == Decimal("62000.0")

    # Second collection should be empty
    assert len(agg.collect_events()) == 0


def test_execute_entry_on_pending_trade():
    """Verify execute_entry mutates WAITING_ENTRY to OPEN and records TradeOpenedEvent."""
    agg = TradeAggregate.create_pending(
        account_id=1,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        target_entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        position_size=Decimal("0.5"),
        leverage=10,
        trade_id=10,
    )
    agg.collect_events()  # Clear waiting event

    # Attach child entry order
    entry_order = OrderAggregate(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        purpose=OrderPurpose.ENTRY,
        quantity=Decimal("0.5"),
        price=Decimal("60000.0"),
    )
    agg.add_order(entry_order)

    agg.execute_entry(fill_price=Decimal("59950.0"), fill_qty=Decimal("0.5"), exchange_order_id="EX123")

    assert agg.status == TradeStatus.OPEN
    assert agg.entry_price == Decimal("59950.0")
    assert agg.opened_at is not None
    assert entry_order.is_filled is True
    assert entry_order.exchange_order_id == "EX123"

    events = agg.collect_events()
    assert len(events) == 1
    assert isinstance(events[0], TradeOpenedEvent)
    assert events[0].entry_price == Decimal("59950.0")


def test_partial_fill_and_pnl_calculation():
    """Verify apply_partial_fill correctly reduces lot, computes realized PnL, and shifts SL."""
    agg = TradeAggregate.create_open(
        account_id=1,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        position_size=Decimal("1.0"),
        leverage=10,
        tp_targets=[Decimal("62000.0"), Decimal("65000.0")],
        trade_id=20,
    )
    agg.collect_events()  # Clear open event

    # TP1 Hit: Close 0.5 BTC at 62000 (+2000 * 0.5 = +1000 USDT)
    tp1_pnl = agg.apply_partial_fill(
        tp_tier=OrderPurpose.TP1,
        fill_price=Decimal("62000.0"),
        fill_qty=Decimal("0.5"),
        new_sl_price=Decimal("60000.0"),  # BEP Shift
    )

    assert tp1_pnl == Decimal("1000.0")
    assert agg.realized_pnl == Decimal("1000.0")
    assert agg.remaining_qty == Decimal("0.5")
    assert agg.sl_price == Decimal("60000.0")
    assert agg.status == TradeStatus.PARTIAL

    events = agg.collect_events()
    assert len(events) == 1
    assert isinstance(events[0], TradePartiallyClosedEvent)
    assert events[0].realized_pnl == Decimal("1000.0")
    assert events[0].remaining_qty == Decimal("0.5")
    assert events[0].new_sl_price == Decimal("60000.0")

    # TP2 Hit: Close 0.3 BTC at 65000 (+5000 * 0.3 = +1500 USDT)
    tp2_pnl = agg.apply_partial_fill(
        tp_tier=OrderPurpose.TP2,
        fill_price=Decimal("65000.0"),
        fill_qty=Decimal("0.3"),
        new_sl_price=Decimal("62000.0"),  # Trailing to TP1
    )

    assert tp2_pnl == Decimal("1500.0")
    assert agg.realized_pnl == Decimal("2500.0")
    assert agg.remaining_qty == Decimal("0.2")
    assert agg.sl_price == Decimal("62000.0")


def test_shift_stop_loss_invariants():
    """Verify stop loss shift enforces risk reduction invariant."""
    # 1. Long position
    long_agg = TradeAggregate.create_open(
        account_id=1,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        position_size=Decimal("1.0"),
        leverage=10,
    )
    long_agg.collect_events()

    # Move SL higher (valid)
    long_agg.shift_stop_loss(new_sl_price=Decimal("59000.0"), reason="TRAILING_STEP_1")
    assert long_agg.sl_price == Decimal("59000.0")
    assert len(long_agg.collect_events()) == 1

    # Move SL lower (invalid -> raises StopLossCannotExceedEntryError)
    with pytest.raises(StopLossCannotExceedEntryError):
        long_agg.shift_stop_loss(new_sl_price=Decimal("57000.0"), reason="INVALID_MOVE")

    # 2. Short position
    short_agg = TradeAggregate.create_open(
        account_id=1,
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("62000.0"),
        position_size=Decimal("1.0"),
        leverage=10,
    )
    short_agg.collect_events()

    # Move SL lower (valid for SHORT)
    short_agg.shift_stop_loss(new_sl_price=Decimal("61000.0"), reason="TRAILING_STEP_1")
    assert short_agg.sl_price == Decimal("61000.0")

    # Move SL higher (invalid for SHORT -> raises StopLossCannotExceedEntryError)
    with pytest.raises(StopLossCannotExceedEntryError):
        short_agg.shift_stop_loss(new_sl_price=Decimal("63000.0"), reason="INVALID_MOVE")


def test_close_trade_aggregate():
    """Verify close completes the trade, calculates final PnL, and records TradeClosedEvent."""
    agg = TradeAggregate.create_open(
        account_id=1,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        position_size=Decimal("0.5"),
        leverage=10,
        trade_id=30,
    )
    agg.collect_events()

    final_pnl = agg.close(exit_price=Decimal("63000.0"), close_reason="FINAL_TP")

    assert final_pnl == Decimal("1500.0")  # (63000 - 60000) * 0.5
    assert agg.realized_pnl == Decimal("1500.0")
    assert agg.remaining_qty == Decimal("0")
    assert agg.status == TradeStatus.CLOSED
    assert agg.close_reason == "FINAL_TP"
    assert agg.closed_at is not None

    events = agg.collect_events()
    assert len(events) == 1
    assert isinstance(events[0], TradeClosedEvent)
    assert events[0].exit_price == Decimal("63000.0")
    assert events[0].total_realized_pnl == Decimal("1500.0")


def test_cancel_pending_trade_aggregate():
    """Verify cancel cancels pending trade and records TradeCancelledEvent."""
    agg = TradeAggregate.create_pending(
        account_id=1,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        target_entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        position_size=Decimal("0.5"),
        leverage=10,
        trade_id=40,
    )
    agg.collect_events()

    agg.cancel(reason="SIGNAL_EXPIRED")

    assert agg.status == TradeStatus.CANCELLED
    assert agg.close_reason == "SIGNAL_EXPIRED"

    events = agg.collect_events()
    assert len(events) == 1
    assert isinstance(events[0], TradeCancelledEvent)
    assert events[0].reason == "SIGNAL_EXPIRED"
