"""Data-access repository for Watchlist management."""

from datetime import datetime
from typing import List, Optional, Union
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.persistence.models import Watchlist, Instrument
from src.presentation.api.schemas.master import WatchlistCreate, WatchlistUpdate
from src.infrastructure.persistence.repositories.base import BaseRepository
from src.domain.ports.repositories import IWatchlistRepository


class WatchlistRepository(BaseRepository[Watchlist, WatchlistCreate, WatchlistUpdate], IWatchlistRepository):
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

    async def get_all_active(self) -> List[Watchlist]:
        """Alias for get_enabled_watchlist_with_instruments."""
        return await self.get_enabled_watchlist_with_instruments()

    async def get_active_watchlist(self) -> List[Watchlist]:
        """Alias for get_enabled_watchlist_with_instruments."""
        return await self.get_enabled_watchlist_with_instruments()

    async def get_all_watchlist_with_instruments(self) -> List[Watchlist]:
        """Fetch all watchlist entries (enabled & disabled) with eagerly loaded Instrument and Leverage Brackets.
        
        Returns:
            List of all Watchlist instances ordered by id ASC.
        """
        stmt = (
            select(Watchlist)
            .options(
                selectinload(Watchlist.instrument).selectinload(Instrument.leverage_brackets)
            )
            .order_by(Watchlist.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_symbol_enabled(
        self,
        instrument_id: Optional[Union[int, str]] = None,
        enabled: bool = True,
        instrument: Optional[Union[int, str]] = None,
    ) -> Watchlist:
        """Add to watchlist or update enabled flag.
        
        Args:
            instrument_id: FK to instruments table or symbol string (e.g. "BTCUSDT").
            enabled: Active trading flag.
            instrument: Backward-compatibility alias for instrument_id.
            
        Returns:
            The created or updated Watchlist instance.
        """
        target = instrument_id if instrument_id is not None else instrument
        if target is None:
            raise ValueError("instrument_id or symbol must be provided.")

        if isinstance(target, str):
            stmt = select(Instrument).where(func.upper(Instrument.symbol) == target.strip().upper()).limit(1)
            res = await self.session.execute(stmt)
            inst = res.scalar_one_or_none()
            if not inst:
                raise ValueError(f"Instrument '{target}' not found in database.")
            inst_id = inst.id
        else:
            inst_id = target

        entry = await self.get_by_instrument_id(inst_id)
        if entry:
            entry.enabled = enabled
            entry.updated_at = datetime.now()
            self.session.add(entry)
        else:
            entry = Watchlist(instrument_id=inst_id, enabled=enabled)
            self.session.add(entry)

        await self.session.flush()
        return entry
