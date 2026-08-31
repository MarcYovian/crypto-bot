"""Data-access repository for per-trade risk breakdown and active exposure."""

from decimal import Decimal
from typing import Optional, List, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.persistence.models import TradeRisk, Trade
from src.presentation.api.schemas.common import BaseSchema
from src.presentation.api.schemas.risk import TradeRiskCreate
from src.infrastructure.persistence.repositories.base import BaseRepository


class TradeRiskRepository(BaseRepository[TradeRisk, TradeRiskCreate, BaseSchema]):
    """CRUD repository for the ``trade_risk`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(TradeRisk, session)

    async def get(self, id: Any) -> Optional[TradeRisk]:
        """Fetch a single record by primary key (trade_id)."""
        return await self.get_by_trade_id(int(id))

    async def get_by_trade_id(self, trade_id: int) -> Optional[TradeRisk]:
        """Fetch risk parameters for a specific trade (trade_id is primary key).
        
        Args:
            trade_id: PK and FK to trades table.
            
        Returns:
            TradeRisk instance or None.
        """
        stmt = select(TradeRisk).where(TradeRisk.trade_id == trade_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_total_active_risk_exposure(self, account_id: int) -> Decimal:
        """Calculate total USDT currently at risk across all active trades.
        
        Active trades have status in ('WAITING_ENTRY', 'OPEN', 'PARTIAL').
        
        Args:
            account_id: FK to trading_accounts table.
            
        Returns:
            Total active USDT risk exposure as Decimal.
        """
        stmt = (
            select(func.coalesce(func.sum(TradeRisk.risk_amount), 0))
            .join(Trade, TradeRisk.trade_id == Trade.id)
            .where(
                Trade.account_id == account_id,
                Trade.status.in_(["WAITING_ENTRY", "OPEN", "PARTIAL"])
            )
        )
        result = await self.session.execute(stmt)
        return Decimal(str(result.scalar_one()))

    async def get_total_margin_used(self, account_id: int) -> Decimal:
        """Calculate total USDT margin currently locked in active positions.
        
        Active positions have status in ('OPEN', 'PARTIAL').
        
        Args:
            account_id: FK to trading_accounts table.
            
        Returns:
            Total locked margin as Decimal.
        """
        stmt = (
            select(func.coalesce(func.sum(TradeRisk.margin), 0))
            .join(Trade, TradeRisk.trade_id == Trade.id)
            .where(
                Trade.account_id == account_id,
                Trade.status.in_(["OPEN", "PARTIAL"])
            )
        )
        result = await self.session.execute(stmt)
        return Decimal(str(result.scalar_one()))

    async def get_trade_risks_by_daily_config(
        self, daily_risk_id: int
    ) -> List[TradeRisk]:
        """Fetch all trade risk allocations associated with a daily snapshot.
        
        Args:
            daily_risk_id: FK to daily_risk_config table.
            
        Returns:
            List of TradeRisk instances.
        """
        stmt = (
            select(TradeRisk)
            .where(TradeRisk.daily_risk_id == daily_risk_id)
            .order_by(TradeRisk.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
