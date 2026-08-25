"""Data-access repository for Exchange Orders."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import Order
from src.schemas.order import OrderCreate, OrderUpdate
from src.repository.base import BaseRepository


class OrderRepository(BaseRepository[Order, OrderCreate, OrderUpdate]):
    """CRUD repository for the ``orders`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(Order, session)

    async def get_by_exchange_order_id(
        self, exchange_order_id: str
    ) -> Optional[Order]:
        """Fetch order by exchange-assigned order ID (e.g. Binance orderId).
        
        Utilizes unique index ``idx_orders_exchange_id``.
        
        Args:
            exchange_order_id: String ID from exchange.
            
        Returns:
            Order instance or None.
        """
        stmt = (
            select(Order)
            .where(Order.exchange_order_id == exchange_order_id)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_client_order_id(
        self, client_order_id: str
    ) -> Optional[Order]:
        """Fetch order by bot-assigned custom client order ID (e.g. "SL_BTC_9981").
        
        Utilizes unique index ``idx_orders_client_id``.
        
        Args:
            client_order_id: String client order ID.
            
        Returns:
            Order instance or None.
        """
        stmt = (
            select(Order)
            .where(Order.client_order_id == client_order_id)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_orders_by_trade_id(self, trade_id: int) -> List[Order]:
        """Fetch all orders attached to a trade position.
        
        Utilizes index ``idx_orders_trade_status``.
        
        Args:
            trade_id: FK to trades table.
            
        Returns:
            List of Order instances ordered by creation time.
        """
        stmt = (
            select(Order)
            .where(Order.trade_id == trade_id)
            .order_by(Order.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_open_orders_by_trade_id(self, trade_id: int) -> List[Order]:
        """Fetch currently active orders ('NEW' or 'PARTIALLY_FILLED') on a trade.
        
        Args:
            trade_id: FK to trades table.
            
        Returns:
            List of active Order instances.
        """
        stmt = (
            select(Order)
            .where(
                Order.trade_id == trade_id,
                Order.status.in_(["NEW", "PARTIALLY_FILLED"])
            )
            .order_by(Order.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_orders_by_purpose(
        self, trade_id: int, purpose: str
    ) -> List[Order]:
        """Fetch orders with a specific purpose ('ENTRY', 'TP1', 'TP2', 'TP3', 'SL').
        
        Args:
            trade_id: FK to trades table.
            purpose: Order purpose string.
            
        Returns:
            List of Order instances.
        """
        stmt = (
            select(Order)
            .where(
                Order.trade_id == trade_id,
                func.upper(Order.purpose) == purpose.strip().upper()
            )
            .order_by(Order.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def cancel_all_open_orders_for_trade(self, trade_id: int) -> int:
        """Bulk update all NEW and PARTIALLY_FILLED orders to CANCELED in DB.
        
        Args:
            trade_id: FK to trades table.
            
        Returns:
            Number of cancelled order rows.
        """
        stmt = (
            update(Order)
            .where(
                Order.trade_id == trade_id,
                Order.status.in_(["NEW", "PARTIALLY_FILLED"])
            )
            .values(status="CANCELED", updated_at=datetime.now())
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return int(getattr(result, "rowcount", 0) or 0)

    async def update_order_fill(
        self,
        exchange_order_id: str,
        status: str,
        filled_qty: Optional[Decimal] = None,
    ) -> Optional[Order]:
        """Atomically update order status and filled quantity from WebSocket message.
        
        Args:
            exchange_order_id: Exchange order identifier.
            status: Target order status string.
            filled_qty: Cumulative filled quantity.
            
        Returns:
            Updated Order instance or None.
        """
        order = await self.get_by_exchange_order_id(exchange_order_id)
        if not order:
            return None

        order.status = status
        if filled_qty is not None:
            order.filled_qty = filled_qty
        order.updated_at = datetime.now()

        self.session.add(order)
        await self.session.commit()
        await self.session.refresh(order)
        return order

    async def cancel_all_active_orders(self) -> int:
        """Bulk update all NEW and PARTIALLY_FILLED orders across all trades to CANCELED.

        Returns:
            Number of cancelled order rows.
        """
        stmt = (
            update(Order)
            .where(Order.status.in_(["NEW", "PARTIALLY_FILLED"]))
            .values(status="CANCELED", updated_at=datetime.now())
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return int(getattr(result, "rowcount", 0) or 0)

