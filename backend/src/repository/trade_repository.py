"""Data-access repository for Trade / Position lifecycle and state machine."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Union, Any
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import Trade, Order, TradeEvent
from src.schemas.trade import TradeCreate, TradeUpdate, TradeStatusUpdate
from src.repository.base import BaseRepository


class TradeRepository(BaseRepository[Trade, TradeCreate, TradeUpdate]):
    """CRUD and lifecycle state-machine repository for the ``trades`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(Trade, session)

    async def get_detail(self, trade_id: int) -> Optional[Trade]:
        """Fetch comprehensive trade detail with all child relationships eagerly loaded.
        
        Loads: instrument, trade_risk, orders, executions, events, and summary via selectinload.
        
        Args:
            trade_id: Trade primary key ID.
            
        Returns:
            Trade instance with populated child relations, or None.
        """
        stmt = (
            select(Trade)
            .options(
                selectinload(Trade.instrument),
                selectinload(Trade.trade_risk),
                selectinload(Trade.orders),
                selectinload(Trade.executions),
                selectinload(Trade.events),
                selectinload(Trade.summary),
            )
            .where(Trade.id == trade_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_trade_by_instrument(
        self, instrument_id: int
    ) -> Optional[Trade]:
        """Check if an active position already exists for this instrument.
        
        Utilizes index ``idx_trades_instrument_status``.
        Active statuses: ('WAITING_ENTRY', 'OPEN', 'PARTIAL').
        
        Args:
            instrument_id: FK to instruments table.
            
        Returns:
            Active Trade instance or None.
        """
        stmt = (
            select(Trade)
            .where(
                Trade.instrument_id == instrument_id,
                Trade.status.in_(["WAITING_ENTRY", "OPEN", "PARTIAL"])
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_active_trades(self, account_id: int) -> int:
        """Count current active positions for risk management limit (max_open_trade).
        
        Args:
            account_id: FK to trading_accounts table.
            
        Returns:
            Count of active positions integer.
        """
        stmt = (
            select(func.count())
            .select_from(Trade)
            .where(
                Trade.account_id == account_id,
                Trade.status.in_(["WAITING_ENTRY", "OPEN", "PARTIAL"])
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    async def get_all_active_trades(
        self, account_id: Optional[int] = None
    ) -> List[Trade]:
        """Fetch all currently active positions across the account.
        
        Args:
            account_id: Optional account FK filter.
            
        Returns:
            List of active Trade instances.
        """
        stmt = (
            select(Trade)
            .where(Trade.status.in_(["WAITING_ENTRY", "OPEN", "PARTIAL"]))
            .order_by(Trade.created_at.desc())
        )
        if account_id is not None:
            stmt = stmt.where(Trade.account_id == account_id)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_trades_with_instrument(
        self, account_id: Optional[int] = None
    ) -> List[Trade]:
        """Fetch active trades with eagerly loaded Instrument metadata for ticker monitoring.
        
        Args:
            account_id: Optional account FK filter.
            
        Returns:
            List of Trade instances with populated .instrument relation.
        """
        stmt = (
            select(Trade)
            .options(selectinload(Trade.instrument))
            .where(Trade.status.in_(["WAITING_ENTRY", "OPEN", "PARTIAL"]))
            .order_by(Trade.created_at.desc())
        )
        if account_id is not None:
            stmt = stmt.where(Trade.account_id == account_id)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_expired_waiting_trades(
        self, max_hours: int = 4
    ) -> List[Trade]:
        """Fetch hanging WAITING_ENTRY trades older than max_hours for cron cancellation.
        
        Utilizes index ``idx_trades_status_created_at``.
        
        Args:
            max_hours: Maximum lifetime in hours for unfilled entry orders.
            
        Returns:
            List of expired WAITING_ENTRY Trade instances.
        """
        cutoff = datetime.now() - timedelta(hours=max_hours)
        stmt = (
            select(Trade)
            .where(
                Trade.status == "WAITING_ENTRY",
                Trade.created_at <= cutoff
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_entry_fill(
        self,
        trade_id: int,
        entry_price: Decimal,
        avg_entry_price: Optional[Decimal] = None,
        opened_at: Optional[datetime] = None,
    ) -> Optional[Trade]:
        """Transition trade from WAITING_ENTRY to OPEN when entry order fills on exchange.
        
        Args:
            trade_id: Trade primary key.
            entry_price: Execution entry price.
            avg_entry_price: Optional average entry price for partial fills.
            opened_at: Position open timestamp.
            
        Returns:
            Updated Trade instance or None.
        """
        trade = await self.get(trade_id)
        if not trade:
            return None

        trade.entry_price = entry_price
        trade.avg_entry_price = avg_entry_price if avg_entry_price is not None else entry_price
        trade.status = "OPEN"
        trade.opened_at = opened_at if opened_at is not None else datetime.now()
        trade.updated_at = datetime.now()

        self.session.add(trade)
        await self.session.commit()
        await self.session.refresh(trade)
        return trade

    async def update_sl_price(
        self, trade_id: int, new_sl_price: Decimal
    ) -> Optional[Trade]:
        """Update Stop Loss price when moving SL to BEP or Trailing Stop.
        
        Args:
            trade_id: Trade primary key.
            new_sl_price: New SL price level.
            
        Returns:
            Updated Trade instance or None.
        """
        trade = await self.get(trade_id)
        if not trade:
            return None

        trade.sl_price = new_sl_price
        trade.updated_at = datetime.now()

        self.session.add(trade)
        await self.session.commit()
        await self.session.refresh(trade)
        return trade

    async def reduce_position_qty(
        self,
        trade_id: int,
        closed_qty: Decimal,
        is_closed: bool = False,
    ) -> Optional[Trade]:
        """Reduce remaining quantity upon partial take profit fill, and auto-close when zero.
        
        Args:
            trade_id: Trade primary key.
            closed_qty: Filled lot quantity to deduct.
            is_closed: Explicit close flag.
            
        Returns:
            Updated Trade instance or None.
        """
        trade = await self.get(trade_id)
        if not trade:
            return None

        new_remaining = Decimal(str(trade.remaining_qty)) - closed_qty
        trade.remaining_qty = max(Decimal("0.0"), new_remaining)

        if trade.remaining_qty <= Decimal("0.0") or is_closed:
            trade.status = "CLOSED"
            trade.closed_at = datetime.now()
        else:
            trade.status = "PARTIAL"

        trade.updated_at = datetime.now()
        self.session.add(trade)
        await self.session.commit()
        await self.session.refresh(trade)
        return trade

    async def update_trade_status(
        self, trade_id: int, schema: "Union[TradeStatusUpdate, str]"
    ) -> Optional[Trade]:
        """Update trade lifecycle status and timestamps.
        
        Args:
            trade_id: Trade primary key.
            schema: TradeStatusUpdate payload or status string.
            
        Returns:
            Updated Trade instance or None.
        """
        trade = await self.get(trade_id)
        if not trade:
            return None

        if isinstance(schema, str):
            trade.status = schema
        else:
            trade.status = schema.status
            if schema.opened_at is not None:
                trade.opened_at = schema.opened_at
            if schema.closed_at is not None:
                trade.closed_at = schema.closed_at

        trade.updated_at = datetime.now()
        self.session.add(trade)
        await self.session.commit()
        await self.session.refresh(trade)
        return trade

    async def create_order(
        self,
        trade_id: int,
        purpose: str,
        order_type: str,
        side: str,
        qty: Any,
        price: Any,
        binance_order_id: str,
    ) -> Order:
        """Record an order under the given trade."""
        order = Order(
            trade_id=trade_id,
            exchange_order_id=binance_order_id,
            client_order_id=f"{purpose}_{trade_id}_{binance_order_id}",
            order_type=order_type,
            purpose=purpose,
            side=side,
            price=Decimal(str(price)),
            qty=Decimal(str(qty)),
            status="NEW",
        )
        self.session.add(order)
        await self.session.commit()
        await self.session.refresh(order)
        return order

    async def log_event(
        self,
        trade_id: int,
        event_type: str,
        payload_json: Optional[str] = None,
    ) -> TradeEvent:
        """Log a lifecycle event for the given trade."""
        event = TradeEvent(
            trade_id=trade_id,
            event_type=event_type,
            payload_json=payload_json,
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def get_closed_trades_history(
        self,
        account_id: int,
        skip: int = 0,
        limit: int = 50,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Trade]:
        """Fetch historical closed and cancelled trades with pagination and date filter.
        
        Args:
            account_id: FK to trading_accounts table.
            skip: Offset.
            limit: Maximum rows.
            start_date: Optional filter start timestamp.
            end_date: Optional filter end timestamp.
            
        Returns:
            List of closed Trade instances ordered by closed_at DESC.
        """
        stmt = (
            select(Trade)
            .where(
                Trade.account_id == account_id,
                Trade.status.in_(["CLOSED", "CANCELLED"])
            )
            .order_by(Trade.closed_at.desc().nullslast(), Trade.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        if start_date is not None:
            stmt = stmt.where(Trade.created_at >= start_date)
        if end_date is not None:
            stmt = stmt.where(Trade.created_at <= end_date)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())