"""Use case for cancelling stale limit orders and marking abandoned trades as CANCELLED."""

from datetime import datetime
import logging
from typing import Optional

from src.domain.ports.gateways import IExchangeGateway
from src.domain.ports.repositories import (
    IInstrumentRepository,
    IOrderRepository,
    ITradeEventRepository,
    ITradeRepository,
)
from src.presentation.api.schemas.trade import TradeStatusUpdate

logger = logging.getLogger(__name__)


class CleanupOrphanOrdersUseCase:
    """Cancels pending WAITING_ENTRY limit orders older than max_age_hours."""

    def __init__(
        self,
        trade_repo: ITradeRepository,
        order_repo: IOrderRepository,
        instrument_repo: IInstrumentRepository,
        trade_event_repo: Optional[ITradeEventRepository] = None,
        exchange_gateway: Optional[IExchangeGateway] = None,
    ) -> None:
        self.trade_repo = trade_repo
        self.order_repo = order_repo
        self.instrument_repo = instrument_repo
        self.trade_event_repo = trade_event_repo
        self.exchange_gateway = exchange_gateway

    async def execute(self, account_id: int = 1, max_age_hours: int = 4) -> int:
        """Cancel expired waiting entry orders on exchange and database."""
        expired_trades = await self.trade_repo.get_expired_waiting_trades(
            max_hours=max_age_hours
        )
        cancelled_count = 0

        for trade in expired_trades:
            if trade.account_id != account_id:
                continue

            # 1. Cancel exchange open orders
            if self.exchange_gateway:
                instrument = await self.instrument_repo.get(trade.instrument_id)
                if instrument:
                    try:
                        if hasattr(self.exchange_gateway, "cancel_all_orders"):
                            await self.exchange_gateway.cancel_all_orders(symbol=instrument.symbol)
                        elif hasattr(self.exchange_gateway, "cancel_all_open_orders"):
                            await self.exchange_gateway.cancel_all_open_orders(symbol=instrument.symbol)
                    except Exception as exc:
                        logger.error("Failed to cancel exchange orders for trade %s: %s", trade.id, exc)

            # 2. Cancel DB open orders
            await self.order_repo.cancel_all_open_orders_for_trade(trade.id)

            # 3. Update trade status to CANCELLED
            await self.trade_repo.update_trade_status(
                trade_id=trade.id,
                schema=TradeStatusUpdate(status="CANCELLED", closed_at=datetime.now()),
            )

            # 4. Log trade event
            if self.trade_event_repo:
                await self.trade_event_repo.log_event(
                    trade_id=trade.id,
                    event_type="ORDER_ERROR",
                    payload={"reason": "ORPHAN_ORDER_TIMEOUT", "max_age_hours": max_age_hours},
                )
            cancelled_count += 1

        if cancelled_count > 0:
            logger.info("Cleaned up %d orphan WAITING_ENTRY trades.", cancelled_count)
        return cancelled_count
