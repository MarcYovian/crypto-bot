"""Data-access repository for DailyRiskConfig snapshots."""

from datetime import date
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.persistence.models import DailyRiskConfig, TradeRisk, Trade
from src.presentation.api.schemas.common import BaseSchema
from src.presentation.api.schemas.risk import DailyRiskConfigCreate
from src.infrastructure.persistence.repositories.base import BaseRepository


class DailyRiskRepository(BaseRepository[DailyRiskConfig, DailyRiskConfigCreate, BaseSchema]):
    """CRUD repository for the ``daily_risk_config`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(DailyRiskConfig, session)

    async def get_by_account_id(
        self, account_id: int, target_date: Optional[date] = None
    ) -> Optional[DailyRiskConfig]:
        """Fetch daily risk snapshot for an account for the given date (default today) or latest.
        
        Args:
            account_id: FK to trading_accounts table.
            target_date: Optional specific calendar date. If None, checks today then latest.
            
        Returns:
            DailyRiskConfig instance or None.
        """
        check_date = target_date or date.today()
        res = await self.get_by_date(account_id, check_date)
        if res:
            return res
        return await self.get_latest_snapshot(account_id)

    async def get_by_date(
        self, account_id: int, snapshot_date: date
    ) -> Optional[DailyRiskConfig]:
        """Fetch locked daily risk snapshot for a specific account and date.
        
        Args:
            account_id: FK to trading_accounts table.
            snapshot_date: Calendar date of the snapshot (YYYY-MM-DD).
            
        Returns:
            DailyRiskConfig instance or None.
        """
        stmt = (
            select(DailyRiskConfig)
            .where(
                DailyRiskConfig.account_id == account_id,
                DailyRiskConfig.date == snapshot_date
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_daily_snapshot(
        self, account_id: int, snapshot_date: date
    ) -> Optional[DailyRiskConfig]:
        """Alias for get_by_date."""
        return await self.get_by_date(account_id, snapshot_date)

    async def get_latest_snapshot(
        self, account_id: int
    ) -> Optional[DailyRiskConfig]:
        """Fetch the most recent daily risk snapshot for an account.
        
        Args:
            account_id: FK to trading_accounts table.
            
        Returns:
            Latest DailyRiskConfig instance or None.
        """
        stmt = (
            select(DailyRiskConfig)
            .where(DailyRiskConfig.account_id == account_id)
            .order_by(DailyRiskConfig.date.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create_daily_snapshot(
        self, schema: DailyRiskConfigCreate
    ) -> DailyRiskConfig:
        """Idempotent snapshot retrieval or creation.
        
        Prevents duplicate daily snapshots if the midnight cron job triggers multiple times.
        
        Args:
            schema: DailyRiskConfigCreate payload.
            
        Returns:
            Existing or newly created DailyRiskConfig instance.
        """
        existing = await self.get_by_date(schema.account_id, schema.date)
        if existing:
            return existing

        return await self.create(schema)

    async def get_daily_history(
        self, account_id: int, start_date: date, end_date: date
    ) -> List[DailyRiskConfig]:
        """Fetch daily equity and risk snapshots within a date range.
        
        Args:
            account_id: FK to trading_accounts table.
            start_date: Start date inclusive.
            end_date: End date inclusive.
            
        Returns:
            List of DailyRiskConfig instances ordered chronologically (date ASC).
        """
        stmt = (
            select(DailyRiskConfig)
            .where(
                DailyRiskConfig.account_id == account_id,
                DailyRiskConfig.date >= start_date,
                DailyRiskConfig.date <= end_date
            )
            .order_by(DailyRiskConfig.date.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_remaining_risk_budget(self, daily_risk_id: int) -> Decimal:
        """Calculate remaining risk budget for the day in USDT.
        
        Formula: max(0, daily_risk_budget - SUM(allocated_active_trade_risk))
        
        Args:
            daily_risk_id: PK of DailyRiskConfig.
            
        Returns:
            Remaining USDT risk budget as Decimal.
        """
        config = await self.get(daily_risk_id)
        if not config:
            return Decimal("0.0")

        stmt = (
            select(func.coalesce(func.sum(TradeRisk.risk_amount), 0))
            .outerjoin(Trade, TradeRisk.trade_id == Trade.id)
            .where(
                TradeRisk.daily_risk_id == daily_risk_id,
                (Trade.status.in_(["WAITING_ENTRY", "OPEN", "PARTIAL"])) | (Trade.id.is_(None)),
            )
        )
        result = await self.session.execute(stmt)
        total_allocated = Decimal(str(result.scalar_one()))

        remaining = Decimal(str(config.risk_amount)) - total_allocated
        return max(Decimal("0.0"), remaining)

    async def get_total_margin_used(self, daily_risk_id: int) -> Decimal:
        """Calculate total margin committed across all trades for the day in USDT.
        
        Args:
            daily_risk_id: PK of DailyRiskConfig.
            
        Returns:
            Total margin used in USDT as Decimal.
        """
        stmt = (
            select(func.coalesce(func.sum(TradeRisk.margin), 0))
            .outerjoin(Trade, TradeRisk.trade_id == Trade.id)
            .where(
                TradeRisk.daily_risk_id == daily_risk_id,
                (Trade.status.in_(["WAITING_ENTRY", "OPEN", "PARTIAL"])) | (Trade.id.is_(None)),
            )
        )
        result = await self.session.execute(stmt)
        return Decimal(str(result.scalar_one()))

