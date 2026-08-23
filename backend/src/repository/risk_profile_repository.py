"""Data-access repository for RiskProfile management."""

from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import RiskProfile
from src.schemas.master import RiskProfileCreate, RiskProfileUpdate
from src.repository.base import BaseRepository


class RiskProfileRepository(BaseRepository[RiskProfile, RiskProfileCreate, RiskProfileUpdate]):
    """CRUD repository for the ``risk_profiles`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(RiskProfile, session)

    async def get_active_profile(self) -> Optional[RiskProfile]:
        """Fetch the current active risk profile configuration.
            
        Returns:
            The active RiskProfile instance or None.
        """
        stmt = (
            select(RiskProfile)
            .where(RiskProfile.is_active.is_(True))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_active_profile(self, profile_id: int) -> Optional[RiskProfile]:
        """Set a single active profile and deactivate all other profiles.
        
        Args:
            profile_id: RiskProfile ID to activate.
            
        Returns:
            The activated RiskProfile instance or None if not found.
        """
        target_profile = await self.get(profile_id)
        if not target_profile:
            return None

        # Deactivate all
        await self.session.execute(
            update(RiskProfile).values(is_active=False)
        )

        # Activate target
        target_profile.is_active = True
        self.session.add(target_profile)
        await self.session.commit()
        await self.session.refresh(target_profile)
        return target_profile
