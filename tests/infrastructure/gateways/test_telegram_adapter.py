"""Comprehensive unit tests for TelegramConnector, TelegramFormatter, and TelegramNotificationAdapter."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
import httpx

from src.infrastructure.gateways.telegram.telegram_connector import TelegramConnector
from src.infrastructure.gateways.telegram.telegram_formatter import TelegramFormatter
from src.infrastructure.gateways.telegram.telegram_adapter import TelegramNotificationAdapter
from src.domain.exceptions.telegram import (
    TelegramError,
    TelegramAuthError,
    TelegramRateLimitError,
    TelegramNetworkError,
    TelegramSendError,
    TelegramMessageParseError,
)


@pytest.fixture
def telegram_gateway():
    connector = TelegramConnector(bot_token="123456:TEST_TOKEN", default_chat_id="12345678")
    formatter = TelegramFormatter()
    adapter = TelegramNotificationAdapter(connector=connector, formatter=formatter)
    return adapter, connector, formatter


@pytest.mark.asyncio
async def test_telegram_send_formatted_message_html(telegram_gateway):
    """Test sending HTML formatted message and parameter structure."""
    adapter, connector, _ = telegram_gateway

    mock_response = httpx.Response(
        status_code=200,
        json={"ok": True, "result": {"message_id": 991, "text": "<b>Hello</b>"}},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage"),
    )

    client = await connector.get_client()
    with patch.object(client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        res = await adapter.send_message(chat_id="12345678", text="<b>Hello</b>", parse_mode="HTML")

        assert res["result"]["message_id"] == 991
        mock_post.assert_called_once()
        called_args, called_kwargs = mock_post.call_args
        assert called_kwargs["json"]["chat_id"] == "12345678"
        assert called_kwargs["json"]["text"] == "<b>Hello</b>"
        assert called_kwargs["json"]["parse_mode"] == "HTML"

    await connector.close()


@pytest.mark.asyncio
async def test_telegram_send_signal_confirmation_with_inline_keyboard(telegram_gateway):
    """Test generating signal confirmation alert with Approve / Reject inline buttons."""
    adapter, connector, _ = telegram_gateway

    mock_response = httpx.Response(
        status_code=200,
        json={"ok": True, "result": {"message_id": 1001}},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage"),
    )

    client = await connector.get_client()
    with patch.object(client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        await adapter.send_signal_confirmation(
            chat_id="12345678",
            signal_id=42,
            symbol="BTCUSDT",
            side="BUY",
            entry_range="60000 - 60500",
            sl=Decimal("59000"),
            tp_targets=[Decimal("61500"), Decimal("63000")],
            confidence=Decimal("0.85"),
        )

        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        assert "BTCUSDT" in payload["text"]
        assert "60000 - 60500" in payload["text"]
        assert "85.0%" in payload["text"]

        keyboard = payload["reply_markup"]["inline_keyboard"]
        assert len(keyboard[0]) == 2
        assert keyboard[0][0]["callback_data"] == "sig_app_42"
        assert keyboard[0][1]["callback_data"] == "sig_rej_42"

    await connector.close()


@pytest.mark.asyncio
async def test_telegram_edit_message_after_user_approval(telegram_gateway):
    """Test editing message content after button interaction."""
    adapter, connector, _ = telegram_gateway

    mock_response = httpx.Response(
        status_code=200,
        json={"ok": True, "result": {"message_id": 1001, "text": "Signal #42 Approved"}},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/editMessageText"),
    )

    client = await connector.get_client()
    with patch.object(client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        res = await adapter.edit_message_text(
            chat_id="12345678",
            message_id=1001,
            text="✅ <b>Signal #42 APPROVED by Admin</b>",
        )

        assert res["result"]["text"] == "Signal #42 Approved"
        payload = mock_post.call_args[1]["json"]
        assert payload["message_id"] == 1001
        assert "APPROVED" in payload["text"]

    await connector.close()


@pytest.mark.asyncio
async def test_telegram_trade_alert_formatters(telegram_gateway):
    """Test formatting and sending Open, TP, SL, and Daily Summary alerts."""
    adapter, connector, _ = telegram_gateway

    mock_response = httpx.Response(
        status_code=200,
        json={"ok": True, "result": {"message_id": 55}},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage"),
    )

    client = await connector.get_client()
    with patch.object(client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        # 1. Trade Opened
        await adapter.send_trade_opened_alert(
            chat_id="123",
            symbol="BTCUSDT",
            side="BUY",
            entry_price=Decimal("60000.0"),
            leverage=20,
            position_size=Decimal("0.1"),
            margin=Decimal("300.0"),
            sl_price=Decimal("59000.0"),
            tp_targets=[Decimal("61500.0"), Decimal("63000.0")],
        )
        assert "POSITION OPENED" in mock_post.call_args[1]["json"]["text"]

        # 2. Take Profit
        await adapter.send_take_profit_alert(
            chat_id="123",
            symbol="BTCUSDT",
            side="BUY",
            tp_level=1,
            exit_price=Decimal("61500.0"),
            closed_qty=Decimal("0.05"),
            realized_pnl=Decimal("75.0"),
            remaining_qty=Decimal("0.05"),
        )
        assert "TAKE PROFIT 1 REACHED" in mock_post.call_args[1]["json"]["text"]

        # 3. Stop Loss
        await adapter.send_stop_loss_alert(
            chat_id="123",
            symbol="BTCUSDT",
            side="BUY",
            exit_price=Decimal("59000.0"),
            closed_qty=Decimal("0.1"),
            realized_pnl=Decimal("-100.0"),
        )
        assert "STOP LOSS TRIGGERED" in mock_post.call_args[1]["json"]["text"]

        # 4. Daily Summary
        await adapter.send_daily_summary_alert(
            chat_id="123",
            date_str="2026-08-14",
            total_trades=5,
            win_count=4,
            loss_count=1,
            win_rate=80.0,
            net_pnl_usdt=Decimal("150.0"),
            profit_factor=2.5,
        )
        assert "DAILY TRADING SCORECARD" in mock_post.call_args[1]["json"]["text"]

    await connector.close()


@pytest.mark.asyncio
async def test_telegram_answer_callback_query(telegram_gateway):
    """Test answering inline keyboard callback interaction."""
    adapter, connector, _ = telegram_gateway

    mock_response = httpx.Response(
        status_code=200,
        json={"ok": True, "result": True},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/answerCallbackQuery"),
    )

    client = await connector.get_client()
    with patch.object(client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        res = await adapter.answer_callback_query("cb_123", text="Sinyal Disetujui")
        assert res["result"] is True
        payload = mock_post.call_args[1]["json"]
        assert payload["callback_query_id"] == "cb_123"
        assert payload["text"] == "Sinyal Disetujui"

    await connector.close()


@pytest.mark.asyncio
async def test_telegram_domain_exceptions_mapping():
    """Test translation of Telegram API errors into Domain Exceptions."""
    connector = TelegramConnector(bot_token="123456:TEST_TOKEN")
    client = await connector.get_client()

    # 1. 401 Unauthorized -> TelegramAuthError
    mock_401 = httpx.Response(
        status_code=401,
        json={"ok": False, "description": "Unauthorized: invalid bot token"},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage"),
    )
    with patch.object(client, "post", new_callable=AsyncMock, return_value=mock_401):
        with pytest.raises(TelegramAuthError):
            await connector.execute_api("sendMessage", {"chat_id": "123", "text": "Test"})

    # 2. 429 Rate Limit -> TelegramRateLimitError
    mock_429 = httpx.Response(
        status_code=429,
        json={"ok": False, "description": "Too Many Requests: retry after 45", "parameters": {"retry_after": 45}},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage"),
    )
    with patch.object(client, "post", new_callable=AsyncMock, return_value=mock_429):
        with pytest.raises(TelegramRateLimitError) as exc_info:
            await connector.execute_api("sendMessage", {"chat_id": "123", "text": "Test"})
        assert exc_info.value.retry_after == 45

    # 3. 400 Chat Not Found -> TelegramSendError
    mock_400_chat = httpx.Response(
        status_code=400,
        json={"ok": False, "description": "Bad Request: chat not found"},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage"),
    )
    with patch.object(client, "post", new_callable=AsyncMock, return_value=mock_400_chat):
        with pytest.raises(TelegramSendError):
            await connector.execute_api("sendMessage", {"chat_id": "123", "text": "Test"})

    # 4. 400 Entity Parse Error -> TelegramMessageParseError
    mock_400_parse = httpx.Response(
        status_code=400,
        json={"ok": False, "description": "Bad Request: can't parse entities in message text"},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage"),
    )
    with patch.object(client, "post", new_callable=AsyncMock, return_value=mock_400_parse):
        with pytest.raises(TelegramMessageParseError):
            await connector.execute_api("sendMessage", {"chat_id": "123", "text": "<unclosed_tag>"})

    # 5. Network Timeout -> TelegramNetworkError
    with patch.object(client, "post", side_effect=httpx.ConnectTimeout("Connection timed out")):
        with pytest.raises(TelegramNetworkError):
            await connector.execute_api("sendMessage", {"chat_id": "123", "text": "Test"})

    await connector.close()


@pytest.mark.asyncio
async def test_telegram_delete_message(telegram_gateway):
    """Test deleteMessage API call parameter structure."""
    adapter, connector, _ = telegram_gateway

    mock_response = httpx.Response(
        status_code=200,
        json={"ok": True, "result": True},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/deleteMessage"),
    )

    client = await connector.get_client()
    with patch.object(client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        res = await adapter.delete_message(chat_id="12345678", message_id=888)

        assert res["ok"] is True
        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        assert payload["chat_id"] == "12345678"
        assert payload["message_id"] == 888

    await connector.close()


def test_format_crypto_price_smart_trimming():
    """Test format_crypto_price eliminates redundant trailing zeroes while maintaining clarity."""
    assert TelegramFormatter.format_crypto_price(Decimal("0.2000000"), precision=7) == "0.20"
    assert TelegramFormatter.format_crypto_price(Decimal("0.1990000"), precision=7) == "0.199"
    assert TelegramFormatter.format_crypto_price(Decimal("0.0010000"), precision=7) == "0.001"
    assert TelegramFormatter.format_crypto_price(Decimal("86.568"), precision=3) == "86.568"
    assert TelegramFormatter.format_crypto_price(Decimal("86.500"), precision=3) == "86.50"
    assert TelegramFormatter.format_crypto_price(Decimal("86.000"), precision=3) == "86.00"
    assert TelegramFormatter.format_crypto_price(Decimal("60000.00"), precision=2) == "60,000.00"
    assert TelegramFormatter.format_crypto_price(Decimal("0.000054300"), precision=7) == "0.0000543"
    assert TelegramFormatter.format_crypto_price(None) == "N/A"


def test_format_crypto_qty_clean():
    """Test format_crypto_qty cleans unnecessary decimals."""
    assert TelegramFormatter.format_crypto_qty(Decimal("28483.000000"), precision=6) == "28483"
    assert TelegramFormatter.format_crypto_qty(Decimal("0.100000"), precision=4) == "0.1"
    assert TelegramFormatter.format_crypto_qty(None) == "0"
