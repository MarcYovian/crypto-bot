"""Use case for emergency panic close of all open trades and order cancellations."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Any

from src.domain.exceptions.system import PanicConfirmationRequiredError
from src.domain.ports.repositories import (
    IBotSettingRepository,
    ITradeRepository,
    IOrderRepository,
)
from src.presentation.api.schemas.system import (
    PanicCloseResponseDTO,
    BotSettingCreate,
    BotSettingUpdate,
)
from src.utils.cache import in_memory_cache
from src.presentation.websocket.ws_manager import ws_manager


class PanicCloseUseCase:
    """Use case to immediately close all active positions, cancel open orders, and pause the bot."""

    def __init__(
        self,
        bot_setting_repo: IBotSettingRepository,
        trade_repo: Optional[ITradeRepository] = None,
        order_repo: Optional[IOrderRepository] = None,
        cache: Optional[Any] = None,
        websocket_manager: Optional[Any] = None,
    ) -> None:
        self.bot_setting_repo = bot_setting_repo
        self.trade_repo = trade_repo
        self.order_repo = order_repo
        self.cache = cache or in_memory_cache
        self.ws_manager = websocket_manager or ws_manager

    async def execute(self, confirmation: bool) -> PanicCloseResponseDTO:
        """Emergency action: close all open positions and cancel active orders."""
        if not confirmation:
            raise PanicConfirmationRequiredError("Emergency panic action requires confirmation=true.")

        closed_trades_count = 0
        canceled_orders_count = 0

        # 1. Close all active positions
        if self.trade_repo:
            active_trades = await self.trade_repo.get_all_active_trades()
            closed_trades_count = len(active_trades)
            now = datetime.now(timezone.utc)
            for trade in active_trades:
                trade.status = "CLOSED"
                trade.remaining_qty = Decimal("0")
                trade.updated_at = now
                if hasattr(self.trade_repo, "session") and self.trade_repo.session:
                    self.trade_repo.session.add(trade)
            if hasattr(self.trade_repo, "session") and self.trade_repo.session:
                await self.trade_repo.session.commit()

        # 2. Cancel all active orders
        if self.order_repo:
            canceled_orders_count = await self.order_repo.cancel_all_active_orders()

        # 3. Set bot to paused
        setting = await self.bot_setting_repo.get_by_key("is_paused")
        if not setting:
            await self.bot_setting_repo.create(
                BotSettingCreate(key="is_paused", value="true", category="SYSTEM", type="BOOL")
            )
        else:
            await self.bot_setting_repo.update(setting, BotSettingUpdate(value="true"))

        # Invalidate caches
        if self.cache:
            await self.cache.invalidate("trades")
            await self.cache.invalidate("settings")
            await self.cache.invalidate("analytics")
            await self.cache.invalidate("signals")
            await self.cache.invalidate("bot:status")

        if self.ws_manager:
            await self.ws_manager.broadcast(
                "CIRCUIT_BREAKER_TRIGGERED",
                {
                    "action": "PANIC_CLOSE",
                    "closed_trades_count": closed_trades_count,
                    "canceled_orders_count": canceled_orders_count,
                },
            )
            await self.ws_manager.broadcast(
                "BOT_STATUS_CHANGED",
                {"is_paused": True, "trading_status": "PAUSED", "action": "PANIC_CLOSE"},
            )

        return PanicCloseResponseDTO(
            success=True,
            closed_trades_count=closed_trades_count,
            canceled_orders_count=canceled_orders_count,
            timestamp=datetime.now(timezone.utc),
        )
