"""Comprehensive unit tests for TelegramNotifierClient and Telegram Domain Exceptions."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
import httpx
from src.clients.telegram_client import TelegramNotifierClient
from src.domain.exceptions.telegram import (
    TelegramError,
    TelegramAuthError,
    TelegramRateLimitError,
    TelegramNetworkError,
    TelegramSendError,
    TelegramMessageParseError,
)


@pytest.mark.asyncio
async def test_telegram_send_formatted_message_html():
    """Test sending HTML formatted message and parameter structure."""
    client = TelegramNotifierClient(bot_token="123456:TEST_TOKEN")

    mock_response = httpx.Response(
        status_code=200,
        json={"ok": True, "result": {"message_id": 991, "text": "<b>Hello</b>"}},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage"),
    )

    with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        res = await client.send_message(chat_id="12345678", text="<b>Hello</b>", parse_mode="HTML")

        assert res["message_id"] == 991
        mock_post.assert_called_once()
        called_args, called_kwargs = mock_post.call_args
        assert called_kwargs["json"]["chat_id"] == "12345678"
        assert called_kwargs["json"]["text"] == "<b>Hello</b>"
        assert called_kwargs["json"]["parse_mode"] == "HTML"

    await client.close()


@pytest.mark.asyncio
async def test_telegram_send_signal_confirmation_with_inline_keyboard():
    """Test generating signal confirmation alert with Approve / Reject inline buttons."""
    client = TelegramNotifierClient(bot_token="123456:TEST_TOKEN")

    mock_response = httpx.Response(
        status_code=200,
        json={"ok": True, "result": {"message_id": 1001}},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage"),
    )

    with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        await client.send_signal_confirmation(
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

    await client.close()


@pytest.mark.asyncio
async def test_telegram_edit_message_after_user_approval():
    """Test editing message content after button interaction."""
    client = TelegramNotifierClient(bot_token="123456:TEST_TOKEN")

    mock_response = httpx.Response(
        status_code=200,
        json={"ok": True, "result": {"message_id": 1001, "text": "Signal #42 Approved"}},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/editMessageText"),
    )

    with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        res = await client.edit_message_text(
            chat_id="12345678",
            message_id=1001,
            text="✅ <b>Signal #42 APPROVED by Admin</b>",
        )

        assert res["text"] == "Signal #42 Approved"
        payload = mock_post.call_args[1]["json"]
        assert payload["message_id"] == 1001
        assert "APPROVED" in payload["text"]

    await client.close()


@pytest.mark.asyncio
async def test_telegram_trade_alert_formatters():
    """Test formatting and sending Open, TP, SL, and Daily Summary alerts."""
    client = TelegramNotifierClient(bot_token="123456:TEST_TOKEN")

    mock_response = httpx.Response(
        status_code=200,
        json={"ok": True, "result": {"message_id": 55}},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage"),
    )

    with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        # 1. Trade Opened
        await client.send_trade_opened_alert(
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
        await client.send_take_profit_alert(
            chat_id="123",
            symbol="BTCUSDT",
            side="BUY",
            tp_level=1,
            exit_price=Decimal("61500.0"),
            closed_qty=Decimal("0.05"),
            realized_pnl=Decimal("75.0"),
            remaining_qty=Decimal("0.05"),
        )
        assert "TAKE PROFIT 1 HIT" in mock_post.call_args[1]["json"]["text"]

        # 3. Stop Loss
        await client.send_stop_loss_alert(
            chat_id="123",
            symbol="BTCUSDT",
            side="BUY",
            exit_price=Decimal("59000.0"),
            closed_qty=Decimal("0.1"),
            realized_pnl=Decimal("-100.0"),
        )
        assert "STOP LOSS TRIGGERED" in mock_post.call_args[1]["json"]["text"]

        # 4. Daily Summary
        await client.send_daily_summary_alert(
            chat_id="123",
            date_str="2026-08-14",
            starting_balance=Decimal("1000.0"),
            ending_balance=Decimal("1150.0"),
            net_pnl=Decimal("150.0"),
            total_trades=5,
            win_rate=80.0,
        )
        assert "DAILY PERFORMANCE SUMMARY" in mock_post.call_args[1]["json"]["text"]

    await client.close()


@pytest.mark.asyncio
async def test_telegram_answer_callback_query():
    """Test answering inline keyboard callback interaction."""
    client = TelegramNotifierClient(bot_token="123456:TEST_TOKEN")

    mock_response = httpx.Response(
        status_code=200,
        json={"ok": True, "result": True},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/answerCallbackQuery"),
    )

    with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        res = await client.answer_callback_query("cb_123", text="Sinyal Disetujui")
        assert res is True
        payload = mock_post.call_args[1]["json"]
        assert payload["callback_query_id"] == "cb_123"
        assert payload["text"] == "Sinyal Disetujui"

    await client.close()


@pytest.mark.asyncio
async def test_telegram_domain_exceptions_mapping():
    """Test translation of Telegram API errors into Domain Exceptions."""
    client = TelegramNotifierClient(bot_token="123456:TEST_TOKEN")

    # 1. 401 Unauthorized -> TelegramAuthError
    mock_401 = httpx.Response(
        status_code=401,
        json={"ok": False, "description": "Unauthorized: invalid bot token"},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage"),
    )
    with patch.object(client.client, "post", new_callable=AsyncMock, return_value=mock_401):
        with pytest.raises(TelegramAuthError):
            await client.send_message(chat_id="123", text="Test")

    # 2. 429 Rate Limit -> TelegramRateLimitError
    mock_429 = httpx.Response(
        status_code=429,
        json={"ok": False, "description": "Too Many Requests: retry after 45", "parameters": {"retry_after": 45}},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage"),
    )
    with patch.object(client.client, "post", new_callable=AsyncMock, return_value=mock_429):
        with pytest.raises(TelegramRateLimitError) as exc_info:
            await client.send_message(chat_id="123", text="Test")
        assert exc_info.value.retry_after == 45

    # 3. 400 Chat Not Found -> TelegramSendError
    mock_400_chat = httpx.Response(
        status_code=400,
        json={"ok": False, "description": "Bad Request: chat not found"},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage"),
    )
    with patch.object(client.client, "post", new_callable=AsyncMock, return_value=mock_400_chat):
        with pytest.raises(TelegramSendError):
            await client.send_message(chat_id="123", text="Test")

    # 4. 400 Entity Parse Error -> TelegramMessageParseError
    mock_400_parse = httpx.Response(
        status_code=400,
        json={"ok": False, "description": "Bad Request: can't parse entities in message text"},
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage"),
    )
    with patch.object(client.client, "post", new_callable=AsyncMock, return_value=mock_400_parse):
        with pytest.raises(TelegramMessageParseError):
            await client.send_message(chat_id="123", text="<unclosed_tag>")

    # 5. Network Timeout -> TelegramNetworkError
    with patch.object(client.client, "post", side_effect=httpx.ConnectTimeout("Connection timed out")):
        with pytest.raises(TelegramNetworkError):
            await client.send_message(chat_id="123", text="Test")

    await client.close()


@pytest.mark.asyncio
async def test_telegram_polling_message_and_caption_normalization():
    """Test that Telegram polling loop correctly extracts text from message text and photo captions."""
    client = TelegramNotifierClient(bot_token="123456:TEST_TOKEN")

    mock_updates = {
        "ok": True,
        "result": [
            {
                "update_id": 100,
                "message": {
                    "message_id": 1,
                    "chat": {"id": 846740826},
                    "text": "/status",
                },
            },
            {
                "update_id": 101,
                "channel_post": {
                    "message_id": 2,
                    "chat": {"id": -100123456},
                    "caption": "🚨 Symbol: SOLUSDT 🟢 Long\n💰 Entry: 140.5",
                },
            },
        ],
    }

    received_messages = []

    async def mock_handler(msg):
        received_messages.append(msg)
        if len(received_messages) == 2:
            client._is_polling = False

    mock_resp = httpx.Response(
        status_code=200,
        json=mock_updates,
        request=httpx.Request("POST", "https://api.telegram.org/bot123456:TEST_TOKEN/getUpdates"),
    )

    with patch.object(client.client, "post", new_callable=AsyncMock, return_value=mock_resp):
        await client.start_polling(on_message_coro=mock_handler)

    assert len(received_messages) == 2
    assert received_messages[0]["text"] == "/status"
    assert "Symbol: SOLUSDT" in received_messages[1]["text"]
    assert received_messages[1]["caption"] == "🚨 Symbol: SOLUSDT 🟢 Long\n💰 Entry: 140.5"

    await client.close()

