"""Use case for resuming trading bot operations and clearing circuit breakers."""

from typing import Optional, Any
from src.domain.ports.repositories import IBotSettingRepository
from src.presentation.api.schemas.system import GenericActionResponse, BotSettingCreate, BotSettingUpdate
from src.utils.cache import in_memory_cache
from src.presentation.websocket.ws_manager import ws_manager


class ResumeBotUseCase:
    """Use case to resume trading bot operations and clear circuit breaker trip."""

    def __init__(
        self,
        bot_setting_repo: IBotSettingRepository,
        cache: Optional[Any] = None,
        websocket_manager: Optional[Any] = None,
    ) -> None:
        self.bot_setting_repo = bot_setting_repo
        self.cache = cache or in_memory_cache
        self.ws_manager = websocket_manager or ws_manager

    async def execute(self) -> GenericActionResponse:
        """Resume bot operations and clear circuit breaker trip status."""
        setting = await self.bot_setting_repo.get_by_key("is_paused")
        if not setting:
            await self.bot_setting_repo.create(
                BotSettingCreate(key="is_paused", value="false", category="SYSTEM", type="BOOL")
            )
        else:
            await self.bot_setting_repo.update(setting, BotSettingUpdate(value="false"))

        cb_setting = await self.bot_setting_repo.get_by_key("circuit_breaker_active")
        if cb_setting:
            await self.bot_setting_repo.update(cb_setting, BotSettingUpdate(value="false"))

        if self.cache:
            await self.cache.invalidate("settings")
            await self.cache.invalidate("bot:status")

        if self.ws_manager:
            await self.ws_manager.broadcast(
                "BOT_STATUS_CHANGED",
                {"is_paused": False, "trading_status": "ACTIVE", "action": "RESUME"},
            )

        return GenericActionResponse(
            success=True,
            message="Trading bot resumed successfully. Signal ingestion active.",
        )
