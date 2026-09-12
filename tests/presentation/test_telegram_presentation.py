"""Unit tests for Telegram Presentation Controller and Wizard Manager."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from src.presentation.telegram.bot_controller import TelegramBotController
from src.presentation.telegram.wizard_manager import TelegramWizardManager, wizard_states
from src.presentation.telegram.formatters import format_crypto_price, format_crypto_qty


def test_telegram_formatters():
    """Verify precision and crypto price/quantity formatters."""
    assert format_crypto_price(65000.5) == "65,000.50"
    assert format_crypto_price(0.00001234) == "0.00001234"
    assert format_crypto_price(None) == "N/A"

    assert format_crypto_qty(1.5000) == "1.5"
    assert format_crypto_qty(0.0000) == "0"
    assert format_crypto_qty(None) == "0"


@pytest.mark.asyncio
async def test_wizard_manager_flow():
    """Test start, env selection, and cancellation of setup wizard."""
    chat_id = 123456789
    mock_session = MagicMock(spec=AsyncSession)
    wm = TelegramWizardManager(mock_session)

    # 1. Start
    res = await wm.start_wizard(chat_id)
    assert "SETUP KREDENSIAL BINANCE" in res["text"]
    assert wm.is_in_wizard(chat_id) is True

    # 2. Select Testnet
    cb_res = await wm.handle_callback(chat_id, "wizard_env_testnet")
    assert "TESTNET" in cb_res["text"]
    assert wizard_states[chat_id]["step"] == "AWAITING_API_KEY"

    # 3. Enter API Key
    key_res = await wm.handle_text_step(chat_id, "my_test_api_key_12345")
    assert "API Key diterima" in key_res
    assert wizard_states[chat_id]["step"] == "AWAITING_API_SECRET"

    # 4. Cancel
    cancel_res = await wm.handle_text_step(chat_id, "/cancel")
    assert "dibatalkan" in cancel_res
    assert wm.is_in_wizard(chat_id) is False


@pytest.mark.asyncio
async def test_bot_controller_slash_command():
    """Test TelegramBotController command routing."""
    mock_session = MagicMock(spec=AsyncSession)
    ctrl = TelegramBotController(mock_session)
    reply = await ctrl.handle_user_message(raw_text="/help", chat_id=98765)
    assert reply is not None
    assert "PERINTAH CRYPTO BOT" in reply


@pytest.mark.asyncio
async def test_telegram_bot_controller_start_polling_task():
    import asyncio
    from unittest.mock import patch, AsyncMock
    from src.infrastructure.di.container import container
    with patch.object(container.telegram_connector, "bot_token", "test_mock_token_123"), \
         patch("src.infrastructure.di.container.container.telegram_connector.start_polling", new_callable=AsyncMock) as mock_poll:
        task = TelegramBotController.start_polling_task()
        assert task is not None
        assert mock_poll.called
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_telegram_bot_controller_image_caption_processing():
    """Verify that photo/media messages with caption are properly extracted and processed."""
    from unittest.mock import patch, AsyncMock
    from src.infrastructure.di.container import container

    captured_coros = {}

    async def fake_start_polling(on_message_coro=None, on_callback_query_coro=None):
        captured_coros["on_message"] = on_message_coro
        captured_coros["on_callback"] = on_callback_query_coro

    with patch.object(container.telegram_connector, "bot_token", "test_mock_token_123"), \
         patch.object(container.telegram_connector, "start_polling", side_effect=fake_start_polling), \
         patch.object(TelegramBotController, "handle_user_message", new_callable=AsyncMock) as mock_handle:
        
        mock_handle.return_value = "Sinyal Diterima"
        task = TelegramBotController.start_polling_task()
        await task

        on_msg = captured_coros.get("on_message")
        assert on_msg is not None

        # Simulate photo message with caption
        photo_msg = {
            "message_id": 1001,
            "chat": {"id": 123456},
            "photo": [{"file_id": "xyz"}],
            "caption": "BTCUSDT BUY Entry 65000 SL 63000 TP 68000",
        }
        await on_msg(photo_msg)

        mock_handle.assert_called_once_with(
            raw_text="BTCUSDT BUY Entry 65000 SL 63000 TP 68000",
            chat_id=123456,
            message_id=1001,
        )



