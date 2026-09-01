"""Tests for Telegram Bot Controller error card formatting upon InsufficientMarginRiskError."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.domain.exceptions import InsufficientMarginRiskError
from src.presentation.telegram.bot_controller import TelegramBotController


@pytest.mark.asyncio
async def test_telegram_approve_callback_insufficient_margin_formatting():
    """Verify that approving a signal with insufficient margin edits message with rich HTML card."""
    mock_session = AsyncMock()
    mock_tg = AsyncMock()
    mock_tg.edit_message_text = AsyncMock()

    controller = TelegramBotController(
        session=mock_session,
        notification_gateway=mock_tg,
    )

    # Mock approve signal use case raising InsufficientMarginRiskError
    controller.approve_signal_use_case = MagicMock()
    controller.approve_signal_use_case.execute = AsyncMock(
        side_effect=InsufficientMarginRiskError(
            required_margin=Decimal("150.00"),
            available_margin=Decimal("25.50"),
            shortfall=Decimal("124.50"),
            position_size=Decimal("0.5"),
            notional=Decimal("1500.00"),
            leverage=10,
            risk_amount=Decimal("30.00"),
            stop_distance=Decimal("60.00"),
            stop_percent=Decimal("2.00"),
            symbol="BTCUSDT",
        )
    )

    res = await controller.handle_callback_query(
        callback_data="approve_signal:42",
        chat_id=12345,
        message_id=999,
    )

    assert "MARGIN TIDAK MENCUKUPI" in res
    assert "150.00 USDT" in res
    assert "25.50 USDT" in res
    assert "124.50 USDT" in res
    assert "1500.00 USDT @ 10x" in res

    # Verify notification_gateway.edit_message_text was called
    mock_tg.edit_message_text.assert_called_once()
    called_kwargs = mock_tg.edit_message_text.call_args.kwargs
    assert called_kwargs["chat_id"] == 12345
    assert called_kwargs["message_id"] == 999
    assert "<b>Detail Perhitungan Margin:</b>" in called_kwargs["text"]
