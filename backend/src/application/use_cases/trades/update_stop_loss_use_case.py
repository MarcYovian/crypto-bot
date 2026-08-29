"""Use case for adjusting Stop Loss price (BEP / Trailing / Manual)."""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from src.application.dto.trade_commands import UpdateStopLossCommand
from src.domain.events.trade_events import StopLossMovedEvent
from src.domain.exceptions import TradeNotFoundError
from src.domain.ports.event_publisher import IDomainEventPublisher
from src.domain.ports.gateways import IExchangeGateway
from src.domain.ports.repositories import IOrderRepository, ITradeEventRepository, ITradeRepository
from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.trade_status import OrderType
from src.presentation.api.schemas.order import OrderCreate

logger = logging.getLogger(__name__)


class UpdateStopLossUseCase:
    """Orchestrates updating a trade's Stop Loss on both database and exchange."""

    def __init__(
        self,
        trade_repo: ITradeRepository,
        order_repo: IOrderRepository,
        trade_event_repo: ITradeEventRepository,
        exchange_gateway: Optional[IExchangeGateway] = None,
        event_publisher: Optional[IDomainEventPublisher] = None,
    ) -> None:
        self.trade_repo = trade_repo
        self.order_repo = order_repo
        self.trade_event_repo = trade_event_repo
        self.exchange_gateway = exchange_gateway
        self.event_publisher = event_publisher

    async def execute(self, cmd: UpdateStopLossCommand) -> Dict[str, Any]:
        """Update stop loss price for an active trade."""
        trade = await self.trade_repo.get(cmd.trade_id)
        if not trade:
            raise TradeNotFoundError(f"Trade #{cmd.trade_id} not found.")

        old_sl = trade.sl_price or trade.entry_price or Decimal("0")
        sym = trade.instrument.symbol if trade.instrument else "BTCUSDT"
        is_long = trade.side.upper() in ("BUY", "LONG")
        exit_side = OrderSide.SELL if is_long else OrderSide.BUY

        # 1. Place new Stop Loss on exchange
        new_order_id = None
        if self.exchange_gateway:
            try:
                sl_resp = await self.exchange_gateway.create_order(
                    symbol=sym,
                    side=exit_side,
                    order_type=OrderType.STOP_MARKET,
                    qty=trade.remaining_qty or trade.position_size,
                    stop_price=cmd.new_sl_price,
                    client_order_id=f"SL_{cmd.reason}_{trade.id}",
                )
                new_order_id = sl_resp.get("exchange_order_id")
                await self.order_repo.create(
                    OrderCreate(
                        trade_id=trade.id,
                        exchange_order_id=new_order_id,
                        client_order_id=f"SL_{cmd.reason}_{trade.id}",
                        order_type="STOP_MARKET",
                        purpose=cmd.reason,
                        side=exit_side.value,
                        price=cmd.new_sl_price,
                        qty=trade.remaining_qty or trade.position_size,
                        status="NEW",
                    )
                )
            except Exception as exc:
                logger.error("Failed to place updated Stop Loss on exchange: %s", exc)

        # 2. Update Trade record in DB
        await self.trade_repo.update_stop_loss(trade.id, cmd.new_sl_price)

        # 3. Log Trade Event
        await self.trade_event_repo.log_event(
            trade_id=trade.id,
            event_type="SL_UPDATE",
            payload={"old_sl": float(old_sl), "new_sl": float(cmd.new_sl_price), "reason": cmd.reason},
        )

        # 4. Dispatch Domain Event
        if self.event_publisher:
            await self.event_publisher.publish(
                StopLossMovedEvent(
                    trade_id=trade.id,
                    account_id=trade.account_id,
                    symbol=sym,
                    old_sl_price=old_sl,
                    new_sl_price=cmd.new_sl_price,
                    reason=cmd.reason,
                )
            )

        return {
            "trade_id": trade.id,
            "symbol": sym,
            "old_sl": float(old_sl),
            "new_sl": float(cmd.new_sl_price),
            "reason": cmd.reason,
        }
