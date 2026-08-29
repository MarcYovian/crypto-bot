"""Unit tests for TelegramNotificationAdapter and TelegramFormatter."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.infrastructure.gateways.telegram import (
    TelegramConnector,
    TelegramFormatter,
    TelegramNotificationAdapter,
)


@pytest.fixture
def mock_tg_connector():
    connector = MagicMock(spec=TelegramConnector)
    connector.default_chat_id = "123456789"
    connector.execute_api = AsyncMock()
    connector.close = AsyncMock()
    return connector


def test_telegram_formatter_pricing():
    assert TelegramFormatter.format_crypto_price(Decimal("65432.10")) == "65,432.10"
    assert TelegramFormatter.format_crypto_price(Decimal("0.00012345")) == "0.00012345"
    assert TelegramFormatter.format_crypto_qty(Decimal("1.50000000")) == "1.5"


def test_telegram_formatter_alert():
    alert_html = TelegramFormatter.format_alert_html(
        title="Circuit Breaker Active",
        message="Trading paused due to daily loss limit.",
        level="CRITICAL",
    )
    assert "CRITICAL ALERT" in alert_html
    assert "Trading paused" in alert_html


@pytest.mark.asyncio
async def test_telegram_adapter_send_message(mock_tg_connector):
    mock_tg_connector.execute_api.return_value = {"ok": True, "result": {"message_id": 1001}}

    adapter = TelegramNotificationAdapter(connector=mock_tg_connector)
    resp = await adapter.send_message(text="Hello Crypto Bot", chat_id=123456789)

    assert resp["ok"] is True
    assert resp["result"]["message_id"] == 1001
    mock_tg_connector.execute_api.assert_awaited_once_with(
        "sendMessage",
        {
            "chat_id": "123456789",
            "text": "Hello Crypto Bot",
            "disable_web_page_preview": True,
            "parse_mode": "HTML",
        },
    )


@pytest.mark.asyncio
async def test_telegram_adapter_edit_message(mock_tg_connector):
    mock_tg_connector.execute_api.return_value = {"ok": True, "result": {"message_id": 1001}}

    adapter = TelegramNotificationAdapter(connector=mock_tg_connector)
    resp = await adapter.edit_message_text(
        chat_id="123456789",
        message_id=1001,
        text="Updated Text",
    )

    assert resp["ok"] is True
    mock_tg_connector.execute_api.assert_awaited_once_with(
        "editMessageText",
        {
            "chat_id": "123456789",
            "message_id": 1001,
            "text": "Updated Text",
            "disable_web_page_preview": True,
            "parse_mode": "HTML",
        },
    )
