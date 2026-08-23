"""Data-access repository for SignalProvider management."""

from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import SignalProvider
from src.schemas.master import SignalProviderCreate, SignalProviderUpdate
from src.repository.base import BaseRepository


class SignalProviderRepository(BaseRepository[SignalProvider, SignalProviderCreate, SignalProviderUpdate]):
    """CRUD repository for the ``signal_providers`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(SignalProvider, session)

    async def get_by_name(self, name: str) -> Optional[SignalProvider]:
        """Fetch signal provider by unique name (case-insensitive).
        
        Args:
            name: Provider name, e.g. "VIP Crypto Signals".
            
        Returns:
            SignalProvider instance or None.
        """
        stmt = select(SignalProvider).where(
            func.upper(SignalProvider.name) == name.strip().upper()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_type(
        self, provider_type: str = "TELEGRAM"
    ) -> List[SignalProvider]:
        """Fetch active signal providers by provider type.
        
        Args:
            provider_type: Provider channel type ("TELEGRAM", "WEBHOOK", "REST_API").
            
        Returns:
            List of active SignalProvider instances.
        """
        stmt = select(SignalProvider).where(
            func.upper(SignalProvider.type) == provider_type.strip().upper(),
            SignalProvider.is_active.is_(True),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
