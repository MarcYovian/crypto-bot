"""Data-access repository for Watchlist management."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import Watchlist, Instrument
from src.schemas.master import WatchlistCreate, WatchlistUpdate
from src.repository.base import BaseRepository


class WatchlistRepository(BaseRepository[Watchlist, WatchlistCreate, WatchlistUpdate]):
    """CRUD repository for the ``watchlist`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(Watchlist, session)

    async def get_by_instrument_id(self, instrument_id: int) -> Optional[Watchlist]:
        """Fetch watchlist entry by instrument ID.
        
        Args:
            instrument_id: FK to instruments table.
            
        Returns:
            Matching Watchlist instance or None.
        """
        stmt = select(Watchlist).where(Watchlist.instrument_id == instrument_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def is_symbol_enabled(self, symbol: str) -> bool:
        """Check if trading is enabled for a given symbol.
        
        Args:
            symbol: Trading pair, e.g. "BTCUSDT".
            
        Returns:
            True if symbol is in watchlist, enabled, and instrument is active.
        """
        stmt = (
            select(Watchlist)
            .join(Instrument, Watchlist.instrument_id == Instrument.id)
            .where(
                func.upper(Instrument.symbol) == symbol.strip().upper(),
                Watchlist.enabled.is_(True),
                Instrument.is_active.is_(True),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_enabled_watchlist_with_instruments(self) -> List[Watchlist]:
        """Fetch all enabled watchlist entries with eagerly loaded Instrument relation.
        
        Returns:
            List of Watchlist instances with populated .instrument field.
        """
        stmt = (
            select(Watchlist)
            .options(selectinload(Watchlist.instrument))
            .where(Watchlist.enabled.is_(True))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_symbol_enabled(
        self, instrument_id: int, enabled: bool
    ) -> Watchlist:
        """Add to watchlist or update enabled flag.
        
        Args:
            instrument_id: FK to instruments table.
            enabled: Active trading flag.
            
        Returns:
            The created or updated Watchlist instance.
        """
        entry = await self.get_by_instrument_id(instrument_id)
        if entry:
            entry.enabled = enabled
            entry.updated_at = datetime.now()
            self.session.add(entry)
        else:
            entry = Watchlist(instrument_id=instrument_id, enabled=enabled)
            self.session.add(entry)

        await self.session.commit()
        await self.session.refresh(entry)
        return entry
