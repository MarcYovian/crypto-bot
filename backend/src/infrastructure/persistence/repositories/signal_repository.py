"""Data-access repository for TradingSignal entity."""

from datetime import datetime
from typing import Optional, List, Tuple, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.infrastructure.persistence.models import TradingSignal
from src.presentation.api.schemas.signal import TradingSignalCreate, TradingSignalUpdate
from src.infrastructure.persistence.repositories.base import BaseRepository
from src.domain.ports.repositories import ISignalRepository


class SignalRepository(BaseRepository[TradingSignal, TradingSignalCreate, TradingSignalUpdate], ISignalRepository):
    """CRUD repository for the ``trading_signals`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(TradingSignal, session)

    async def get(self, id: Any) -> Optional[TradingSignal]:
        """Fetch signal by primary key with eager-loaded relationships."""
        stmt = (
            select(TradingSignal)
            .options(
                selectinload(TradingSignal.instrument),
                selectinload(TradingSignal.provider),
            )
            .where(TradingSignal.id == id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

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

    async def get_signals_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> Tuple[int, List[TradingSignal]]:
        """Fetch signals feed with optional status filter and pagination.

        Args:
            page: Current page (1-based).
            page_size: Number of items per page.
            status: Optional lifecycle or OpenAPI status filter (e.g. RECEIVED, EXECUTED, PENDING, PROCESSED).

        Returns:
            Tuple of (total_count, list of TradingSignal models with eager-loaded instrument & provider).
        """
        stmt = (
            select(TradingSignal)
            .options(
                selectinload(TradingSignal.instrument),
                selectinload(TradingSignal.provider),
            )
        )
        count_stmt = select(func.count(TradingSignal.id))

        if status:
            clean_status = status.strip().upper()
            if clean_status == "PENDING":
                stmt = stmt.where(TradingSignal.status.in_(["RECEIVED", "PENDING"]))
                count_stmt = count_stmt.where(TradingSignal.status.in_(["RECEIVED", "PENDING"]))
            elif clean_status == "PROCESSED":
                stmt = stmt.where(TradingSignal.status.in_(["EXECUTED", "PROCESSED"]))
                count_stmt = count_stmt.where(TradingSignal.status.in_(["EXECUTED", "PROCESSED"]))
            else:
                stmt = stmt.where(TradingSignal.status == clean_status)
                count_stmt = count_stmt.where(TradingSignal.status == clean_status)

        total_res = await self.session.execute(count_stmt)
        total_count: int = total_res.scalar_one() or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(TradingSignal.created_at.desc()).offset(offset).limit(page_size)

        signals_res = await self.session.execute(stmt)
        signals = list(signals_res.scalars().all())

        return total_count, signals