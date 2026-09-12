"""Data-access repository for SignalProvider management."""

from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.persistence.models import SignalProvider
from src.presentation.api.schemas.master import SignalProviderCreate, SignalProviderUpdate
from src.infrastructure.persistence.repositories.base import BaseRepository
from src.infrastructure.persistence.models.trading_signals import TradingSignal
from src.infrastructure.persistence.models.trades import Trade
from src.infrastructure.persistence.models.trade_summaries import TradeSummary
from src.domain.ports.repositories import ISignalProviderRepository


class SignalProviderRepository(BaseRepository[SignalProvider, SignalProviderCreate, SignalProviderUpdate], ISignalProviderRepository):
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

    async def get_all_providers(self) -> List[SignalProvider]:
        """Fetch all signal providers ordered by id ASC.
        
        Returns:
            List of all SignalProvider instances.
        """
        stmt = select(SignalProvider).order_by(SignalProvider.id.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_provider_performance_summary(self, provider_id: int) -> Dict[str, Any]:
        """Aggregate total signals, executed trades count, win rate, and total net PnL in a single SQL query.

        Args:
            provider_id: Signal provider primary key.

        Returns:
            Dict with keys: total_signals, executed_trades, win_rate, total_net_pnl_usdt.
        """

        # 1. Total signals count
        sig_count_stmt = select(func.count(TradingSignal.id)).where(TradingSignal.provider_id == provider_id)
        sig_res = await self.session.execute(sig_count_stmt)
        total_signals: int = sig_res.scalar_one() or 0

        # 2. Executed trades & PnL aggregation in 1 single join query
        trade_stmt = (
            select(
                func.count(Trade.id).label("executed_trades"),
                func.sum(case((TradeSummary.result == "WIN", 1), else_=0)).label("winning_trades"),
                func.coalesce(func.sum(TradeSummary.net_pnl), 0).label("total_net_pnl"),
            )
            .join(TradingSignal, Trade.signal_id == TradingSignal.id)
            .outerjoin(TradeSummary, Trade.id == TradeSummary.trade_id)
            .where(TradingSignal.provider_id == provider_id)
        )
        trade_res = await self.session.execute(trade_stmt)
        row = trade_res.mappings().one()

        executed_trades: int = row["executed_trades"] or 0
        winning_trades: int = row["winning_trades"] or 0
        total_net_pnl = float(row["total_net_pnl"] or 0.0)
        win_rate = round((winning_trades / executed_trades) * 100, 2) if executed_trades > 0 else 0.0

        return {
            "total_signals": total_signals,
            "executed_trades": executed_trades,
            "win_rate": win_rate,
            "total_net_pnl_usdt": total_net_pnl,
        }

