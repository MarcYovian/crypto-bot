"""Data-access repository for the TradingAccount entity."""

from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.persistence.models import TradingAccount
from src.presentation.api.schemas.master import TradingAccountCreate, TradingAccountUpdate
from src.infrastructure.persistence.repositories.base import BaseRepository
from src.domain.ports.repositories import ITradingAccountRepository


class TradingAccountRepository(BaseRepository[TradingAccount, TradingAccountCreate, TradingAccountUpdate], ITradingAccountRepository):
    """CRUD repository for the ``trading_accounts`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(TradingAccount, session)

    async def get_active_account(self, exchange_id: int = 1) -> Optional[TradingAccount]:
        """Fetch the primary active account for an exchange.
        
        Args:
            exchange_id: FK to exchanges table.
            
        Returns:
            The active TradingAccount instance, or None.
        """
        stmt = (
            select(TradingAccount)
            .where(
                TradingAccount.exchange_id == exchange_id,
                TradingAccount.is_active.is_(True)
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_environment(self, environment: str = "MAINNET") -> List[TradingAccount]:
        """Fetch accounts by trading environment (MAINNET or TESTNET).
        
        Args:
            environment: "MAINNET" or "TESTNET".
            
        Returns:
            List of matching TradingAccount instances.
        """
        stmt = (
            select(TradingAccount)
            .where(
                func.upper(TradingAccount.environment) == environment.strip().upper(),
                TradingAccount.is_active.is_(True)
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_account_with_credentials(self, account_id: int) -> Optional[TradingAccount]:
        """Fetch account with eagerly loaded API credentials.
        
        Args:
            account_id: TradingAccount primary key ID.
            
        Returns:
            TradingAccount with populated .credentials relation.
        """
        stmt = (
            select(TradingAccount)
            .options(selectinload(TradingAccount.credentials))
            .where(TradingAccount.id == account_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[TradingAccount]:
        """Fetch trading account by name/label."""
        stmt = select(TradingAccount).where(TradingAccount.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
