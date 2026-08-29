from decimal import Decimal
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.persistence.models import RiskProfile
from src.presentation.api.schemas.master import RiskProfileCreate, RiskProfileUpdate
from src.infrastructure.persistence.repositories.base import BaseRepository


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

    async def get_or_create_default_profile(self) -> RiskProfile:
        """Fetch the active risk profile or create/activate a standard DEFAULT profile."""
        active = await self.get_active_profile()
        if active:
            return active

        # Check if a DEFAULT named profile exists
        stmt = select(RiskProfile).where(RiskProfile.name == "DEFAULT").limit(1)
        res = await self.session.execute(stmt)
        existing_default = res.scalar_one_or_none()
        if existing_default:
            existing_default.is_active = True
            self.session.add(existing_default)
            await self.session.commit()
            await self.session.refresh(existing_default)
            return existing_default

        # Create new default profile (2.0% risk, 5.0% max daily loss, 3 max open trades)
        default_profile = await self.create(
            RiskProfileCreate(
                name="DEFAULT",
                risk_percent=Decimal("2.0"),
                max_daily_loss=Decimal("5.0"),
                max_open_trade=3,
                is_active=True,
            )
        )
        return default_profile

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

