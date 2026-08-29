"""Data-access repository for Trade / Position lifecycle and state machine."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Union, Any
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.persistence.models import Trade, Order, TradeEvent
from src.presentation.api.schemas.trade import TradeCreate, TradeUpdate, TradeStatusUpdate
from src.infrastructure.persistence.repositories.base import BaseRepository


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

    async def get_with_instrument(self, trade_id: int) -> Optional[Trade]:
        """Fetch a Trade with only its associated Instrument preloaded.
        
        Args:
            trade_id: Trade primary key ID.
            
        Returns:
            Trade instance with populated instrument relation, or None.
        """
        stmt = (
            select(Trade)
            .options(selectinload(Trade.instrument))
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
        from datetime import timezone
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=max_hours)
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
        filled_qty: Optional[Decimal] = None,
    ) -> Optional[Trade]:
        trade = await self.get(trade_id)
        if not trade:
            return None

        trade.entry_price = entry_price
        trade.avg_entry_price = avg_entry_price if avg_entry_price is not None else entry_price
        if filled_qty is not None and filled_qty > Decimal("0"):
            trade.position_size = filled_qty
            trade.remaining_qty = filled_qty
        trade.status = "OPEN"
        trade.opened_at = opened_at if opened_at is not None else datetime.now()
        trade.updated_at = datetime.now()

        self.session.add(trade)
        await self.session.commit()
        return await self.get_with_instrument(trade.id) or trade


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
        return await self.get_with_instrument(trade.id) or trade

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
        return await self.get_with_instrument(trade.id) or trade

    async def update_partial_close(
        self,
        trade_id: int,
        closed_qty: Decimal,
        remaining_qty: Optional[Decimal] = None,
        realized_pnl: Optional[Decimal] = None,
    ) -> Optional[Trade]:
        """Update trade on partial TP fill."""
        trade = await self.get(trade_id)
        if not trade:
            return None
        if remaining_qty is not None:
            trade.remaining_qty = max(Decimal("0.0"), remaining_qty)
        else:
            new_rem = Decimal(str(trade.remaining_qty or trade.position_size)) - closed_qty
            trade.remaining_qty = max(Decimal("0.0"), new_rem)

        if trade.remaining_qty <= Decimal("0.0"):
            trade.status = "CLOSED"
            trade.closed_at = datetime.now()
        else:
            trade.status = "PARTIAL"

        trade.updated_at = datetime.now()
        self.session.add(trade)
        await self.session.commit()
        return await self.get_with_instrument(trade.id) or trade

    async def update_stop_loss(self, trade_id: int, new_sl_price: Decimal) -> Optional[Trade]:
        """Alias for update_sl_price."""
        return await self.update_sl_price(trade_id=trade_id, new_sl_price=new_sl_price)

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
        return await self.get_with_instrument(trade.id) or trade

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

    async def get_active_positions_with_relations(self, account_id: int) -> List[Trade]:
        """Fetch active trades with instrument, orders, and events eagerly loaded.
        
        Args:
            account_id: Trading account ID.
            
        Returns:
            List of active Trade entities.
        """
        stmt = (
            select(Trade)
            .options(
                selectinload(Trade.instrument),
                selectinload(Trade.events),
                selectinload(Trade.orders),
            )
            .where(
                Trade.account_id == account_id,
                Trade.status.in_(["WAITING_ENTRY", "OPEN", "PARTIAL"]),
            )
            .order_by(Trade.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_history_paginated(
        self,
        account_id: int,
        page: int = 1,
        page_size: int = 20,
        symbol: Optional[str] = None,
        result: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> tuple[int, List[Trade]]:
        """Fetch paginated closed/cancelled trades with total count and filters.
        
        Args:
            account_id: Trading account ID.
            page: Current page number (1-based).
            page_size: Maximum records per page.
            symbol: Optional ticker filter.
            result: Optional outcome filter (WIN, LOSS, BREAKEVEN, CANCELLED).
            start_date: Optional start datetime filter.
            end_date: Optional end datetime filter.
            
        Returns:
            Tuple of (total_matching_count, list_of_trade_entities).
        """
        from src.infrastructure.persistence.models.instruments import Instrument
        from src.infrastructure.persistence.models.trade_summaries import TradeSummary

        stmt = (
            select(Trade)
            .options(
                selectinload(Trade.instrument),
                selectinload(Trade.summary),
            )
            .where(
                Trade.account_id == account_id,
                Trade.status.in_(["CLOSED", "CANCELLED"]),
            )
        )

        count_stmt = select(func.count(Trade.id)).where(
            Trade.account_id == account_id,
            Trade.status.in_(["CLOSED", "CANCELLED"]),
        )

        if symbol:
            clean_symbol = symbol.strip().upper()
            stmt = stmt.join(Trade.instrument).where(Instrument.symbol == clean_symbol)
            count_stmt = count_stmt.join(Trade.instrument).where(Instrument.symbol == clean_symbol)

        if result:
            clean_result = result.strip().upper()
            if clean_result == "CANCELLED":
                stmt = stmt.where(Trade.status == "CANCELLED")
                count_stmt = count_stmt.where(Trade.status == "CANCELLED")
            else:
                stmt = stmt.join(Trade.summary).where(TradeSummary.result == clean_result)
                count_stmt = count_stmt.join(Trade.summary).where(TradeSummary.result == clean_result)

        if start_date:
            stmt = stmt.where(Trade.created_at >= start_date)
            count_stmt = count_stmt.where(Trade.created_at >= start_date)

        if end_date:
            stmt = stmt.where(Trade.created_at <= end_date)
            count_stmt = count_stmt.where(Trade.created_at <= end_date)

        total_res = await self.session.execute(count_stmt)
        total_count: int = total_res.scalar_one() or 0

        offset = max(0, (page - 1) * page_size)
        stmt = stmt.order_by(Trade.closed_at.desc().nullslast(), Trade.created_at.desc()).offset(offset).limit(page_size)
        trades_res = await self.session.execute(stmt)
        trades = list(trades_res.scalars().all())

        return total_count, trades

    async def get_closed_trades_for_report(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Trade]:
        """Fetch all closed trades with eager loaded instrument and summary for reporting.

        Args:
            start_date: Optional start timestamp filter on closed_at / created_at.
            end_date: Optional end timestamp filter on closed_at / created_at.

        Returns:
            List of Trade instances ordered by closed_at descending.
        """
        stmt = (
            select(Trade)
            .options(
                selectinload(Trade.instrument),
                selectinload(Trade.summary),
                selectinload(Trade.executions),
            )
            .where(Trade.status == "CLOSED")
            .order_by(Trade.closed_at.desc().nullslast(), Trade.id.desc())
        )

        if start_date is not None:
            clean_start = start_date.replace(tzinfo=None) if getattr(start_date, "tzinfo", None) else start_date
            stmt = stmt.where(
                (Trade.closed_at >= clean_start) | ((Trade.closed_at.is_(None)) & (Trade.created_at >= clean_start))
            )
        if end_date is not None:
            clean_end = end_date.replace(tzinfo=None) if getattr(end_date, "tzinfo", None) else end_date
            stmt = stmt.where(
                (Trade.closed_at <= clean_end) | ((Trade.closed_at.is_(None)) & (Trade.created_at <= clean_end))
            )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())