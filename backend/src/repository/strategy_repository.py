"""Data-access repository for Strategy management."""

from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import Strategy
from src.schemas.master import StrategyCreate, StrategyUpdate
from src.repository.base import BaseRepository


class StrategyRepository(BaseRepository[Strategy, StrategyCreate, StrategyUpdate]):
    """CRUD repository for the ``strategies`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(Strategy, session)

    async def get_by_name(self, name: str) -> Optional[Strategy]:
        """Fetch strategy by unique name (case-insensitive).
        
        Args:
            name: Strategy identifier name.
            
        Returns:
            Strategy instance or None.
        """
        stmt = select(Strategy).where(
            func.upper(Strategy.name) == name.strip().upper()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_strategies(self) -> List[Strategy]:
        """Fetch all active strategies.
        
        Returns:
            List of active Strategy instances.
        """
        stmt = select(Strategy).where(Strategy.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
