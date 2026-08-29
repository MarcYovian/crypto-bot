"""Data-access repository for Trade Executions / Order Fills."""

from decimal import Decimal
from typing import List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.persistence.models import Execution
from src.presentation.api.schemas.common import BaseSchema
from src.presentation.api.schemas.order import ExecutionCreate
from src.infrastructure.persistence.repositories.base import BaseRepository


class ExecutionRepository(BaseRepository[Execution, ExecutionCreate, BaseSchema]):
    """CRUD repository for the ``executions`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(Execution, session)

    async def get_executions_by_trade_id(self, trade_id: int) -> List[Execution]:
        """Fetch all execution fills for a trade ordered chronologically.
        
        Utilizes index ``idx_executions_trade_time``.
        
        Args:
            trade_id: FK to trades table.
            
        Returns:
            List of Execution instances ordered by executed_at ASC.
        """
        stmt = (
            select(Execution)
            .where(Execution.trade_id == trade_id)
            .order_by(Execution.executed_at.asc(), Execution.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_executions_by_order_id(self, order_id: int) -> List[Execution]:
        """Fetch execution fills for a specific order.
        
        Args:
            order_id: FK to orders table.
            
        Returns:
            List of Execution instances.
        """
        stmt = (
            select(Execution)
            .where(Execution.order_id == order_id)
            .order_by(Execution.executed_at.asc(), Execution.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_total_commission_by_trade(self, trade_id: int) -> Decimal:
        """Calculate total exchange commissions paid across all fills of a trade.
        
        Args:
            trade_id: FK to trades table.
            
        Returns:
            Sum of commissions as Decimal.
        """
        stmt = (
            select(func.coalesce(func.sum(Execution.commission), 0))
            .where(Execution.trade_id == trade_id)
        )
        result = await self.session.execute(stmt)
        return Decimal(str(result.scalar_one()))

    async def get_total_realized_pnl_by_trade(self, trade_id: int) -> Decimal:
        """Calculate cumulative realized profit and loss from all closing fills of a trade.
        
        Args:
            trade_id: FK to trades table.
            
        Returns:
            Sum of realized PnL as Decimal.
        """
        stmt = (
            select(func.coalesce(func.sum(Execution.realized_pnl), 0))
            .where(Execution.trade_id == trade_id)
        )
        result = await self.session.execute(stmt)
        return Decimal(str(result.scalar_one()))
