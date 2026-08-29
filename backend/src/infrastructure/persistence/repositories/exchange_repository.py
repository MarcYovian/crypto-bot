"""Data-access repository for the Exchange master entity."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.persistence.models import Exchange
from src.presentation.api.schemas.master import ExchangeCreate, ExchangeUpdate
from src.infrastructure.persistence.repositories.base import BaseRepository


class ExchangeRepository(BaseRepository[Exchange, ExchangeCreate, ExchangeUpdate]):
    """CRUD repository for the ``exchanges`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(Exchange, session)

    async def get_by_code(self, code: str) -> Optional[Exchange]:
        """Fetch an exchange by unique code (case-insensitive).
        
        Args:
            code: Exchange code, e.g. "BINANCE", "BYBIT".
            
        Returns:
            The Exchange instance if found, None otherwise.
        """
        stmt = select(Exchange).where(func.upper(Exchange.code) == code.strip().upper())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Exchange]:
        """Fetch an exchange by name (case-insensitive).
        
        Args:
            name: Exchange name.
            
        Returns:
            The Exchange instance if found, None otherwise.
        """
        stmt = select(Exchange).where(func.upper(Exchange.name) == name.strip().upper())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_exchanges(self) -> List[Exchange]:
        """Fetch all exchanges with active status (status = True).
        
        Returns:
            List of active Exchange instances.
        """
        stmt = select(Exchange).where(Exchange.status.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def toggle_status(self, id: int, status: bool) -> Optional[Exchange]:
        """Enable or disable an exchange.
        
        Args:
            id: Exchange primary key ID.
            status: Boolean status to set.
            
        Returns:
            The updated Exchange instance, or None if not found.
        """
        exchange = await self.get(id)
        if not exchange:
            return None

        exchange.status = status
        exchange.updated_at = datetime.now()
        self.session.add(exchange)
        await self.session.commit()
        await self.session.refresh(exchange)
        return exchange
