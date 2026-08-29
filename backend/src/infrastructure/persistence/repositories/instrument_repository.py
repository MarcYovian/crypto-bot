"""Data-access repository for trading Instruments (symbol metadata and precision)."""

from datetime import datetime
from typing import Optional, List, Union, Dict, Any, Sequence
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.persistence.models import Instrument
from src.presentation.api.schemas.master import InstrumentCreate, InstrumentUpdate
from src.infrastructure.persistence.repositories.base import BaseRepository


class InstrumentRepository(BaseRepository[Instrument, InstrumentCreate, InstrumentUpdate]):
    """CRUD repository for the ``instruments`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(Instrument, session)

    async def get_by_symbol(
        self, symbol: str, exchange_id: Optional[int] = None
    ) -> Optional[Instrument]:
        """Fetch instrument metadata by trading pair symbol with eagerly loaded leverage brackets.
        
        Args:
            symbol: Trading pair, e.g. "BTCUSDT".
            exchange_id: Optional exchange FK filter.
            
        Returns:
            Matching Instrument instance or None.
        """
        stmt = (
            select(Instrument)
            .options(selectinload(Instrument.leverage_brackets))
            .where(func.upper(Instrument.symbol) == symbol.strip().upper())
        )
        if exchange_id is not None:
            stmt = stmt.where(Instrument.exchange_id == exchange_id)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_active(
        self, exchange_id: Optional[int] = None
    ) -> List[Instrument]:
        """Fetch all active instruments.
        
        Args:
            exchange_id: Optional exchange FK filter.
            
        Returns:
            List of active Instrument instances.
        """
        stmt = select(Instrument).where(Instrument.is_active.is_(True))
        if exchange_id is not None:
            stmt = stmt.where(Instrument.exchange_id == exchange_id)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_instruments_with_brackets(
        self, exchange_id: Optional[int] = None
    ) -> List[Instrument]:
        """Fetch all active instruments with eagerly loaded leverage brackets.
        
        Args:
            exchange_id: Optional exchange FK filter.
            
        Returns:
            List of active Instrument instances with populated leverage_brackets relation.
        """
        stmt = (
            select(Instrument)
            .options(selectinload(Instrument.leverage_brackets))
            .where(Instrument.is_active.is_(True))
            .order_by(Instrument.symbol.asc())
        )
        if exchange_id is not None:
            stmt = stmt.where(Instrument.exchange_id == exchange_id)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def bulk_upsert_instruments(
        self, instruments: Sequence[Union[InstrumentCreate, Dict[str, Any]]]
    ) -> int:
        """Insert or update instrument metadata synced from exchange info.
        
        Args:
            instruments: List of InstrumentCreate schemas or dictionaries.
            
        Returns:
            Number of processed instrument records.
        """
        count = 0
        for item in instruments:
            data = item.model_dump() if isinstance(item, InstrumentCreate) else item.copy()
            symbol = data.get("symbol", "").strip().upper()
            exchange_id = data.get("exchange_id")

            existing = await self.get_by_symbol(symbol, exchange_id)
            if existing:
                for k, v in data.items():
                    setattr(existing, k, v)
                existing.updated_at = datetime.now()
                self.session.add(existing)
            else:
                new_inst = Instrument(**data)
                self.session.add(new_inst)
            count += 1

        await self.session.commit()
        return count
