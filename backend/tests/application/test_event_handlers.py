"""Unit tests for decoupled TradeNotificationEventHandler."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.event_handlers.trade_event_handlers import TradeNotificationEventHandler
from src.domain.events.trade_events import (
    StopLossMovedEvent,
    TradeClosedEvent,
    TradeOpenedEvent,
    TradePartiallyClosedEvent,
)
from src.domain.ports.gateways import INotificationGateway
from src.domain.value_objects.side import OrderSide


@pytest.fixture
def mock_notif_gateway():
    gateway = MagicMock(spec=INotificationGateway)
    gateway.send_message = AsyncMock()
    gateway.send_trade_opened_alert = AsyncMock()
    gateway.send_take_profit_alert = AsyncMock()
    gateway.send_stop_loss_moved_alert = AsyncMock()
    gateway.send_trade_closed_alert = AsyncMock()
    return gateway


@pytest.mark.asyncio
async def test_on_trade_opened_event_handler(mock_notif_gateway):
    handler = TradeNotificationEventHandler(notification_gateway=mock_notif_gateway)

    event = TradeOpenedEvent(
        trade_id=101,
        account_id=1,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        entry_price=Decimal("65000.0"),
        position_size=Decimal("0.5"),
        leverage=10,
        sl_price=Decimal("63000.0"),
        tp1_price=Decimal("67000.0"),
    )

    with patch("src.application.event_handlers.trade_event_handlers.ws_manager.broadcast", new_callable=AsyncMock) as mock_ws:
        await handler.on_trade_opened(event)
        mock_notif_gateway.send_trade_opened_alert.assert_awaited_once()
        mock_ws.assert_awaited_once_with(
            "TRADE_OPENED",
            {
                "trade_id": 101,
                "symbol": "BTCUSDT",
                "side": "BUY",
                "entry_price": 65000.0,
                "position_size": 0.5,
                "leverage": 10,
                "sl_price": 63000.0,
            },
        )


@pytest.mark.asyncio
async def test_on_trade_closed_event_handler(mock_notif_gateway):
    handler = TradeNotificationEventHandler(notification_gateway=mock_notif_gateway)

    event = TradeClosedEvent(
        trade_id=101,
        account_id=1,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        exit_price=Decimal("67000.0"),
        closed_qty=Decimal("0.5"),
        total_realized_pnl=Decimal("1000.0"),
        close_reason="TAKE_PROFIT_ALL",
    )

    with patch("src.application.event_handlers.trade_event_handlers.ws_manager.broadcast", new_callable=AsyncMock) as mock_ws:
        await handler.on_trade_closed(event)
        mock_notif_gateway.send_trade_closed_alert.assert_awaited_once()
        mock_ws.assert_awaited_once_with(
            "TRADE_CLOSED",
            {
                "trade_id": 101,
                "symbol": "BTCUSDT",
                "close_price": 67000.0,
                "pnl": 1000.0,
                "close_reason": "TAKE_PROFIT_ALL",
            },
        )
