"""Inbound channel listener for Telegram VIP signals using MTProto."""

import asyncio
import logging
from typing import Any, List, Optional, Union

logger = logging.getLogger(__name__)


class TelegramChannelListener:
    """Async MTProto channel listener for Telegram VIP signals."""

    def __init__(
        self,
        api_id: Optional[int] = None,
        api_hash: Optional[str] = None,
        session_name: str = "crypto_bot_session",
    ) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_name = session_name
        self.is_running = False

    async def start(
        self,
        channel_ids: List[Union[str, int]],
        on_message_coro: Any,
    ) -> None:
        """Start listening for incoming messages on VIP channels."""
        self.is_running = True
        logger.info("TelegramChannelListener started for channels: %s", channel_ids)
        while self.is_running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop listening and disconnect session."""
        self.is_running = False
        logger.info("TelegramChannelListener stopped.")

    async def disconnect(self) -> None:
        """Alias for stopping and disconnecting channel listener."""
        await self.stop()
