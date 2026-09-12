"""Unit tests for InMemoryDomainEventPublisher."""

import pytest
from decimal import Decimal
from src.domain.events.trade_events import TradeOpenedEvent
from src.domain.value_objects.side import OrderSide
from src.infrastructure.events.in_memory_event_publisher import InMemoryDomainEventPublisher


@pytest.mark.asyncio
async def test_event_publisher_subscribe_and_publish():
    bus = InMemoryDomainEventPublisher()
    received_events = []

    async def on_trade_opened(event: TradeOpenedEvent):
        received_events.append(event)

    bus.subscribe(TradeOpenedEvent, on_trade_opened)

    event = TradeOpenedEvent(
        trade_id=101,
        account_id=1,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        entry_price=Decimal("65000"),
        position_size=Decimal("0.5"),
        leverage=10,
        sl_price=Decimal("63000"),
    )

    await bus.publish(event)

    assert len(received_events) == 1
    assert received_events[0].trade_id == 101
    assert received_events[0].symbol == "BTCUSDT"


@pytest.mark.asyncio
async def test_event_publisher_multiple_handlers_and_error_shielding():
    bus = InMemoryDomainEventPublisher()
    calls = []

    async def failing_handler(event):
        calls.append("failing")
        raise RuntimeError("Handler failed on purpose")

    async def succeeding_handler(event):
        calls.append("succeeding")

    bus.subscribe(TradeOpenedEvent, failing_handler)
    bus.subscribe(TradeOpenedEvent, succeeding_handler)

    event = TradeOpenedEvent(
        trade_id=102,
        account_id=1,
        symbol="ETHUSDT",
        side=OrderSide.SELL,
        entry_price=Decimal("3500"),
        position_size=Decimal("1.0"),
        leverage=20,
        sl_price=Decimal("3600"),
    )

    # Should not raise exception despite failing_handler error
    await bus.publish(event)

    assert "failing" in calls
    assert "succeeding" in calls
