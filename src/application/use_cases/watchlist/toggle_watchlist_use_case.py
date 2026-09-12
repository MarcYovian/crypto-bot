"""Use case for toggling active trading whitelist status for a coin pair."""

import logging
from typing import Optional, Any

from src.domain.exceptions.trade import SymbolNotWhitelistedError
from src.domain.ports.repositories import IWatchlistRepository, IInstrumentRepository
from src.presentation.api.schemas.master import WatchlistItemDTO

logger = logging.getLogger(__name__)


class ToggleWatchlistUseCase:
    """Use case to enable or disable active trading for a specific coin pair."""

    def __init__(
        self,
        watchlist_repo: IWatchlistRepository,
        instrument_repo: IInstrumentRepository,
        sync_instruments_use_case: Optional[Any] = None,
    ) -> None:
        self.watchlist_repo = watchlist_repo
        self.instrument_repo = instrument_repo
        self.sync_instruments_use_case = sync_instruments_use_case

    async def execute(self, symbol: str, enabled: bool) -> WatchlistItemDTO:
        """Enable or disable active trading for a specific coin pair."""
        clean_symbol = symbol.strip().upper().replace("/", "").replace(":USDT", "")

        inst = await self.instrument_repo.get_by_symbol(clean_symbol)
        if not inst and self.sync_instruments_use_case:
            if hasattr(self.sync_instruments_use_case, "get_or_sync_instrument"):
                inst = await self.sync_instruments_use_case.get_or_sync_instrument(clean_symbol)

        if not inst:
            raise SymbolNotWhitelistedError(
                f"Symbol '{clean_symbol}' is not a valid active USDT contract on Binance Futures."
            )

        updated_entry = await self.watchlist_repo.set_symbol_enabled(inst.id, enabled)

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
