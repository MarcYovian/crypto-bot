"""Watchlist business service for managing whitelisted trading pairs and leverage tiers."""

import logging
from typing import List, Optional

from src.schemas.master import WatchlistItemDTO
from src.repository.watchlist_repository import WatchlistRepository
from src.repository.instrument_repository import InstrumentRepository
from src.services.instrument_service import InstrumentService
from src.domain.exceptions.trade import SymbolNotWhitelistedError

logger = logging.getLogger(__name__)


class WatchlistService:
    """Service orchestrating trading pair whitelist enrollment, enabled status toggling, and metadata."""

    def __init__(
        self,
        watchlist_repo: WatchlistRepository,
        instrument_repo: InstrumentRepository,
        instrument_service: Optional[InstrumentService] = None,
    ) -> None:
        self.watchlist_repo = watchlist_repo
        self.instrument_repo = instrument_repo
        self.instrument_service = instrument_service

    async def get_watchlist(self) -> List[WatchlistItemDTO]:
        """Fetch all watchlist entries with resolved precision and maximum leverage tiers.

        Returns:
            List of WatchlistItemDTO objects.
        """
        entries = await self.watchlist_repo.get_all_watchlist_with_instruments()
        result: List[WatchlistItemDTO] = []

        for item in entries:
            inst = item.instrument
            if not inst:
                continue

            max_lev = 125
            if inst.leverage_brackets:
                max_lev = max(b.initial_leverage for b in inst.leverage_brackets)

            result.append(
                WatchlistItemDTO(
                    id=item.id,
                    symbol=inst.symbol,
                    enabled=item.enabled,
                    max_leverage=max_lev,
                    tick_size=float(inst.tick_size),
                    min_qty=float(inst.min_qty),
                )
            )

        return result

    async def toggle_watchlist(self, symbol: str, enabled: bool) -> WatchlistItemDTO:
        """Enable or disable active trading for a specific coin pair.

        If the instrument does not yet exist locally, attempts dynamic on-demand resolution
        via InstrumentService from Binance Futures metadata.

        Args:
            symbol: Trading pair symbol (e.g. "BTCUSDT").
            enabled: Active trading flag.

        Returns:
            Updated WatchlistItemDTO.

        Raises:
            SymbolNotWhitelistedError: If the symbol cannot be resolved or is invalid.
        """
        clean_symbol = symbol.strip().upper().replace("/", "").replace(":USDT", "")

        # 1. Resolve Instrument
        inst = await self.instrument_repo.get_by_symbol(clean_symbol)
        if not inst and self.instrument_service:
            inst = await self.instrument_service.get_or_sync_instrument(clean_symbol)

        if not inst:
            raise SymbolNotWhitelistedError(
                f"Symbol '{clean_symbol}' is not a valid active USDT contract on Binance Futures."
            )

        # 2. Update status in Watchlist
        updated_entry = await self.watchlist_repo.set_symbol_enabled(inst.id, enabled)

        # 3. Resolve max leverage
        max_lev = 125
        if inst.leverage_brackets:
            max_lev = max(b.initial_leverage for b in inst.leverage_brackets)

        logger.info(f"Watchlist pair {clean_symbol} toggled to enabled={enabled}")

        return WatchlistItemDTO(
            id=updated_entry.id,
            symbol=inst.symbol,
            enabled=updated_entry.enabled,
            max_leverage=max_lev,
            tick_size=float(inst.tick_size),
            min_qty=float(inst.min_qty),
        )
