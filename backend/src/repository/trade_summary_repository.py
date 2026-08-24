"""Data-access repository for Trade Summaries and performance aggregation."""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import TradeSummary, Trade
from src.schemas.common import BaseSchema
from src.schemas.event_summary import TradeSummaryCreate
from src.repository.base import BaseRepository


class TradeSummaryRepository(BaseRepository[TradeSummary, TradeSummaryCreate, BaseSchema]):
    """CRUD and performance analytics repository for the ``trade_summaries`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(TradeSummary, session)

    async def get_by_trade_id(self, trade_id: int) -> Optional[TradeSummary]:
        """Fetch summary performance metrics for a specific trade.
        
        Args:
            trade_id: PK and FK to trades table.
            
        Returns:
            TradeSummary instance or None.
        """
        stmt = select(TradeSummary).where(TradeSummary.trade_id == trade_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_performance_summary(
        self,
        account_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Compute aggregate performance statistics.
        
        Calculates total trades, win rate, gross & net PnL, commissions, funding,
        average R:R, and profit factor.
        
        Args:
            account_id: Optional account FK filter.
            start_date: Optional start datetime filter on closed_at.
            end_date: Optional end datetime filter on closed_at.
            
        Returns:
            Dictionary containing aggregated performance metrics.
        """
        # Base query with optional join to Trade for account filtering
        stmt = select(
            func.count(TradeSummary.trade_id).label("total_trades"),
            func.sum(case((TradeSummary.result == "WIN", 1), else_=0)).label("winning_trades"),
            func.sum(case((TradeSummary.result == "LOSS", 1), else_=0)).label("losing_trades"),
            func.sum(case((TradeSummary.result == "BREAKEVEN", 1), else_=0)).label("breakeven_trades"),
            func.coalesce(func.sum(TradeSummary.gross_pnl), 0).label("total_gross_pnl"),
            func.coalesce(func.sum(TradeSummary.net_pnl), 0).label("total_net_pnl"),
            func.coalesce(func.sum(TradeSummary.commission), 0).label("total_commission"),
            func.coalesce(func.sum(TradeSummary.funding), 0).label("total_funding"),
            func.coalesce(func.avg(TradeSummary.rr), 0).label("avg_rr"),
            func.coalesce(func.sum(case((TradeSummary.gross_pnl > 0, TradeSummary.gross_pnl), else_=0)), 0).label("total_win_gross"),
            func.coalesce(func.sum(case((TradeSummary.gross_pnl < 0, func.abs(TradeSummary.gross_pnl)), else_=0)), 0).label("total_loss_gross"),
        )

        if account_id is not None:
            stmt = stmt.join(Trade, TradeSummary.trade_id == Trade.id).where(Trade.account_id == account_id)

        if start_date is not None:
            stmt = stmt.where(TradeSummary.closed_at >= start_date)
        if end_date is not None:
            stmt = stmt.where(TradeSummary.closed_at <= end_date)

        result = await self.session.execute(stmt)
        row = result.mappings().one()

        total = row["total_trades"] or 0
        wins = row["winning_trades"] or 0
        losses = row["losing_trades"] or 0
        beps = row["breakeven_trades"] or 0
        win_rate = round((wins / total) * 100, 2) if total > 0 else 0.0

        total_win_gross = Decimal(str(row["total_win_gross"]))
        total_loss_gross = Decimal(str(row["total_loss_gross"]))
        profit_factor = round(float(total_win_gross / total_loss_gross), 2) if total_loss_gross > Decimal("0") else (float("inf") if total_win_gross > 0 else 0.0)

        return {
            "total_trades": total,
            "winning_trades": wins,
            "losing_trades": losses,
            "breakeven_trades": beps,
            "win_rate": win_rate,
            "total_gross_pnl": Decimal(str(row["total_gross_pnl"])),
            "total_net_pnl": Decimal(str(row["total_net_pnl"])),
            "total_commission": Decimal(str(row["total_commission"])),
            "total_funding": Decimal(str(row["total_funding"])),
            "avg_rr": round(float(row["avg_rr"]), 2),
            "profit_factor": profit_factor,
        }

    async def get_best_and_worst_trade(
        self, account_id: Optional[int] = None
    ) -> Dict[str, Optional[TradeSummary]]:
        """Fetch the most profitable trade and largest losing trade.
        
        Args:
            account_id: Optional account FK filter.
            
        Returns:
            Dictionary with keys 'best_trade' and 'worst_trade'.
        """
        best_stmt = select(TradeSummary)
        worst_stmt = select(TradeSummary)

        if account_id is not None:
            best_stmt = best_stmt.join(Trade, TradeSummary.trade_id == Trade.id).where(Trade.account_id == account_id)
            worst_stmt = worst_stmt.join(Trade, TradeSummary.trade_id == Trade.id).where(Trade.account_id == account_id)

        best_stmt = best_stmt.order_by(TradeSummary.net_pnl.desc()).limit(1)
        worst_stmt = worst_stmt.order_by(TradeSummary.net_pnl.asc()).limit(1)

        best_res = await self.session.execute(best_stmt)
        worst_res = await self.session.execute(worst_stmt)

        return {
            "best_trade": best_res.scalar_one_or_none(),
            "worst_trade": worst_res.scalar_one_or_none(),
        }

    async def get_recent_summaries(
        self, account_id: Optional[int] = None, limit: int = 20
    ) -> List[TradeSummary]:
        """Fetch recent completed trade summaries.
        
        Args:
            account_id: Optional account FK filter.
            limit: Maximum rows.
            
        Returns:
            List of TradeSummary instances ordered by closed_at DESC.
        """
        stmt = select(TradeSummary).order_by(TradeSummary.closed_at.desc()).limit(limit)
        if account_id is not None:
            stmt = stmt.join(Trade, TradeSummary.trade_id == Trade.id).where(Trade.account_id == account_id)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_daily_pnl_map(
        self,
        account_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[date, float]:
        """Aggregate net PnL grouped by closed_at date in a single SQL query (O(1) roundtrip).

        Args:
            account_id: Optional account FK filter.
            start_date: Optional start datetime filter.
            end_date: Optional end datetime filter.

        Returns:
            Dictionary of {date_object: float_net_pnl}.
        """
        stmt = select(
            func.date(TradeSummary.closed_at).label("trade_date"),
            func.sum(TradeSummary.net_pnl).label("total_net_pnl"),
        )
        if account_id is not None:
            stmt = stmt.join(Trade, TradeSummary.trade_id == Trade.id).where(Trade.account_id == account_id)

        if start_date is not None:
            stmt = stmt.where(TradeSummary.closed_at >= start_date)
        if end_date is not None:
            stmt = stmt.where(TradeSummary.closed_at <= end_date)

        stmt = stmt.group_by(func.date(TradeSummary.closed_at))

        result = await self.session.execute(stmt)
        rows = result.all()

        pnl_map: Dict[date, float] = {}
        for row in rows:
            raw_date = row[0]
            val = float(row[1] or 0.0)
            if isinstance(raw_date, str):
                d = datetime.strptime(raw_date, "%Y-%m-%d").date()
            elif isinstance(raw_date, datetime):
                d = raw_date.date()
            elif isinstance(raw_date, date):
                d = raw_date
            else:
                continue
            pnl_map[d] = val

        return pnl_map
