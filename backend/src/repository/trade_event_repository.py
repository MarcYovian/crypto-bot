"""Data-access repository for Trade Events audit timeline."""

import json
from datetime import datetime
from typing import Optional, List, Union, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import TradeEvent
from src.schemas.common import BaseSchema
from src.schemas.event_summary import TradeEventCreate
from src.repository.base import BaseRepository


class TradeEventRepository(BaseRepository[TradeEvent, TradeEventCreate, BaseSchema]):
    """CRUD repository for the ``trade_events`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(TradeEvent, session)

    async def log_event(
        self,
        trade_id: int,
        event_type: str,
        payload: Optional[Union[str, Dict[str, Any]]] = None,
        created_at: Optional[datetime] = None,
    ) -> TradeEvent:
        """Helper to append an audit timeline event for a trade.
        
        Args:
            trade_id: FK to trades table.
            event_type: Valid event type string.
            payload: Optional JSON string or Python dictionary payload.
            created_at: Optional explicit creation timestamp.
            
        Returns:
            The newly created TradeEvent instance.
        """
        payload_str: Optional[str] = None
        if payload is not None:
            if isinstance(payload, dict):
                payload_str = json.dumps(payload)
            else:
                payload_str = str(payload)

        event = TradeEvent(
            trade_id=trade_id,
            event_type=event_type.strip().upper(),
            payload_json=payload_str,
            created_at=created_at if created_at is not None else datetime.now(),
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def get_events_by_trade(self, trade_id: int) -> List[TradeEvent]:
        """Fetch full timeline of events for a trade ordered chronologically.
        
        Utilizes index ``idx_trade_events_trade_time``.
        
        Args:
            trade_id: FK to trades table.
            
        Returns:
            List of TradeEvent instances ordered by created_at ASC.
        """
        stmt = (
            select(TradeEvent)
            .where(TradeEvent.trade_id == trade_id)
            .order_by(TradeEvent.created_at.asc(), TradeEvent.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_event_by_trade(
        self, trade_id: int
    ) -> Optional[TradeEvent]:
        """Fetch the most recent event for a trade to inspect position milestone.
        
        Args:
            trade_id: FK to trades table.
            
        Returns:
            Latest TradeEvent instance or None.
        """
        stmt = (
            select(TradeEvent)
            .where(TradeEvent.trade_id == trade_id)
            .order_by(TradeEvent.created_at.desc(), TradeEvent.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_events_by_type(
        self, event_type: str, limit: int = 50
    ) -> List[TradeEvent]:
        """Fetch recent events of a specific type across all trades.
        
        Args:
            event_type: Event type string.
            limit: Maximum rows to return.
            
        Returns:
            List of TradeEvent instances ordered by created_at DESC.
        """
        stmt = (
            select(TradeEvent)
            .where(func.upper(TradeEvent.event_type) == event_type.strip().upper())
            .order_by(TradeEvent.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
