"""Data-access repository for TradingSignal entity."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import TradingSignal
from src.schemas.signal import TradingSignalCreate, TradingSignalUpdate
from src.repository.base import BaseRepository


class SignalRepository(BaseRepository[TradingSignal, TradingSignalCreate, TradingSignalUpdate]):
    """CRUD repository for the ``trading_signals`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(TradingSignal, session)

    async def get_by_telegram_message_id(
        self, message_id: int
    ) -> Optional[TradingSignal]:
        """Fetch signal by its unique Telegram message ID for deduplication.
        
        Args:
            message_id: Original Telegram message ID.
            
        Returns:
            TradingSignal instance or None if not found.
        """
        stmt = (
            select(TradingSignal)
            .where(TradingSignal.telegram_message_id == message_id)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def has_active_signal(
        self, instrument_id: int, side: str
    ) -> bool:
        """Check if an active signal already exists for this pair and side.
        
        Active statuses: 'RECEIVED' or 'EXECUTED'.
        
        Args:
            instrument_id: FK to instruments table.
            side: 'BUY' or 'SELL'.
            
        Returns:
            True if an active signal exists, False otherwise.
        """
        stmt = (
            select(TradingSignal)
            .where(
                TradingSignal.instrument_id == instrument_id,
                func.upper(TradingSignal.side) == side.strip().upper(),
                TradingSignal.status.in_(["RECEIVED", "EXECUTED"])
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_pending_confirmation_signals(self) -> List[TradingSignal]:
        """Fetch all signals awaiting manual user confirmation via Telegram buttons.
        
        Returns:
            List of TradingSignal instances with confirmation_status == 'PENDING'.
        """
        stmt = (
            select(TradingSignal)
            .where(TradingSignal.confirmation_status == "PENDING")
            .order_by(TradingSignal.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_confirmation_status(
        self, signal_id: int, confirmation_status: str
    ) -> Optional[TradingSignal]:
        """Update user confirmation status ('APPROVED' or 'REJECTED').
        
        Args:
            signal_id: Signal primary key.
            confirmation_status: 'APPROVED' or 'REJECTED'.
            
        Returns:
            Updated TradingSignal instance or None.
        """
        signal = await self.get(signal_id)
        if not signal:
            return None

        signal.confirmation_status = confirmation_status.strip().upper()
        signal.updated_at = datetime.now()
        self.session.add(signal)
        await self.session.commit()
        await self.session.refresh(signal)
        return signal

    async def update_status(
        self, signal_id: int, status: str
    ) -> Optional[TradingSignal]:
        """Update signal lifecycle status ('RECEIVED', 'EXECUTED', 'CANCELLED', 'EXPIRED').
        
        Args:
            signal_id: Signal primary key.
            status: Target status string.
            
        Returns:
            Updated TradingSignal instance or None.
        """
        signal = await self.get(signal_id)
        if not signal:
            return None

        signal.status = status.strip().upper()
        signal.updated_at = datetime.now()
        self.session.add(signal)
        await self.session.commit()
        await self.session.refresh(signal)
        return signal

    async def get_signals_by_instrument(
        self, instrument_id: int, limit: int = 50
    ) -> List[TradingSignal]:
        """Fetch recent signals for a specific trading pair.
        
        Args:
            instrument_id: FK to instruments table.
            limit: Maximum signals to return.
            
        Returns:
            List of TradingSignal instances.
        """
        stmt = (
            select(TradingSignal)
            .where(TradingSignal.instrument_id == instrument_id)
            .order_by(TradingSignal.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())