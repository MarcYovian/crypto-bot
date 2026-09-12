"""Unit tests for domain events."""

from decimal import Decimal
from src.domain.events.trade_events import TradeOpenedEvent, StopLossMovedEvent, TradeClosedEvent
from src.domain.events.order_events import OrderFilledEvent
from src.domain.events.signal_events import SignalReceivedEvent
from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.trade_status import OrderPurpose


def test_trade_opened_event_creation():
    evt = TradeOpenedEvent(
        trade_id=101,
        account_id=1,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        entry_price=Decimal("65000"),
        position_size=Decimal("0.5"),
        leverage=10,
        sl_price=Decimal("63000"),
        tp1_price=Decimal("67000"),
    )

    assert evt.event_name == "TradeOpenedEvent"
    assert evt.trade_id == 101
    assert evt.symbol == "BTCUSDT"
    assert evt.event_id.startswith("evt-")
    assert evt.trace_id.startswith("trc-")

    d = evt.to_dict()
    assert d["event_name"] == "TradeOpenedEvent"
    assert d["trade_id"] == 101


def test_trade_lifecycle_events():
    from src.domain.events.trade_events import (
        TradeWaitingEntryEvent,
        TradePartiallyClosedEvent,
        TradeClosedEvent,
        TradeCancelledEvent,
    )
    from src.domain.value_objects.side import MarginMode
    from src.domain.value_objects.trade_status import TradeStatus

    # Waiting Entry
    wait_evt = TradeWaitingEntryEvent(
        trade_id=102,
        account_id=1,
        symbol="ETHUSDT",
        side=OrderSide.SELL,
        target_entry_price=Decimal("3500"),
        position_size=Decimal("1.5"),
        leverage=20,
        sl_price=Decimal("3600"),
        margin_mode=MarginMode.ISOLATED,
    )
    assert wait_evt.symbol == "ETHUSDT"
    assert wait_evt.margin_mode == MarginMode.ISOLATED

    # Partially closed
    part_evt = TradePartiallyClosedEvent(
        trade_id=101,
        account_id=1,
        symbol="BTCUSDT",
        target_hit=OrderPurpose.TP1,
        fill_price=Decimal("67000"),
        closed_qty=Decimal("0.25"),
        remaining_qty=Decimal("0.25"),
        realized_pnl=Decimal("500"),
        new_sl_price=Decimal("65000"),
    )
    assert part_evt.target_hit == OrderPurpose.TP1
    assert part_evt.realized_pnl == Decimal("500")

    # Trade closed
    close_evt = TradeClosedEvent(
        trade_id=101,
        account_id=1,
        symbol="BTCUSDT",
        exit_price=Decimal("70000"),
        total_realized_pnl=Decimal("1250"),
        close_reason="FINAL_TP",
        status=TradeStatus.CLOSED,
    )
    assert close_evt.status == TradeStatus.CLOSED
    assert close_evt.close_reason == "FINAL_TP"

    # Trade cancelled
    cancel_evt = TradeCancelledEvent(
        trade_id=102,
        account_id=1,
        symbol="ETHUSDT",
        reason="CANCELLED_BY_OPERATOR",
    )
    assert cancel_evt.status == TradeStatus.CANCELLED



def test_order_filled_event():
    evt = OrderFilledEvent(
        order_id=501,
        trade_id=101,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        purpose=OrderPurpose.ENTRY,
        fill_price=Decimal("65000"),
        fill_qty=Decimal("0.5"),
        fee=Decimal("1.25"),
        fee_asset="USDT",
    )

    assert evt.purpose == OrderPurpose.ENTRY
    assert evt.fill_qty == Decimal("0.5")


def test_order_created_event():
    from src.domain.events.order_events import OrderCreatedEvent
    from src.domain.value_objects.trade_status import OrderType

    evt = OrderCreatedEvent(
        order_id=501,
        trade_id=101,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        purpose=OrderPurpose.ENTRY,
        price=Decimal("65000"),
        qty=Decimal("0.5"),
        client_order_id="cl-12345",
    )

    assert evt.order_type == OrderType.LIMIT
    assert evt.purpose == OrderPurpose.ENTRY
    assert evt.side == OrderSide.BUY


def test_order_partially_filled_event():
    from src.domain.events.order_events import OrderPartiallyFilledEvent
    from src.domain.value_objects.trade_status import OrderStatus

    evt = OrderPartiallyFilledEvent(
        order_id=501,
        trade_id=101,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        purpose=OrderPurpose.ENTRY,
        fill_price=Decimal("65000"),
        fill_qty=Decimal("0.2"),
        remaining_qty=Decimal("0.3"),
        cumulative_filled_qty=Decimal("0.2"),
    )

    assert evt.status == OrderStatus.PARTIALLY_FILLED
    assert evt.remaining_qty == Decimal("0.3")


def test_order_cancelled_event():
    from src.domain.events.order_events import OrderCancelledEvent
    from src.domain.value_objects.trade_status import OrderStatus

    evt = OrderCancelledEvent(
        order_id=501,
        trade_id=101,
        symbol="BTCUSDT",
        purpose=OrderPurpose.SL,
        client_order_id="cl-12345",
        reason="MANUAL_CANCEL",
    )

    assert evt.status == OrderStatus.CANCELED
    assert evt.reason == "MANUAL_CANCEL"


def test_stop_loss_moved_event():
    evt = StopLossMovedEvent(
        trade_id=101,
        account_id=1,
        symbol="BTCUSDT",
        old_sl_price=Decimal("63000"),
        new_sl_price=Decimal("65000"),
        reason="BEP_AFTER_TP1",
    )

    assert evt.reason == "BEP_AFTER_TP1"
    assert evt.new_sl_price == Decimal("65000")


def test_signal_events():
    from src.domain.events.signal_events import (
        SignalReceivedEvent,
        SignalApprovedEvent,
        SignalRejectedEvent,
        SignalExecutionFailedEvent,
    )
    from src.domain.value_objects.trade_status import OrderType

    sig_rcv = SignalReceivedEvent(
        signal_id=1,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        entry_min=Decimal("65000"),
        entry_max=Decimal("65200"),
        sl_price=Decimal("63000"),
        tp_targets=[Decimal("67000"), Decimal("70000")],
        confidence_score=0.95,
        raw_text="BUY BTCUSDT @ 65000",
    )
    assert sig_rcv.order_type == OrderType.LIMIT
    assert sig_rcv.symbol == "BTCUSDT"
    assert len(sig_rcv.tp_targets) == 2

    sig_app = SignalApprovedEvent(
        signal_id=1,
        symbol="BTCUSDT",
        approved_by="admin",
        entry_price=Decimal("65000"),
        sl_price=Decimal("63000"),
        calculated_lot_size=Decimal("0.5"),
        leverage=10,
    )
    assert sig_app.approved_by == "admin"
    assert sig_app.calculated_lot_size == Decimal("0.5")

    sig_rej = SignalRejectedEvent(
        signal_id=1,
        symbol="BTCUSDT",
        reason="Risk limit exceeded",
    )
    assert sig_rej.reason == "Risk limit exceeded"

    sig_fail = SignalExecutionFailedEvent(
        signal_id=1,
        symbol="BTCUSDT",
        error_message="Exchange insufficient margin",
    )
    assert sig_fail.error_message == "Exchange insufficient margin"


