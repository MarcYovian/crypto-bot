"""Use case for retrieving all whitelisted trading pairs with leverage tiers."""

from typing import List

from src.domain.ports.repositories import IWatchlistRepository
from src.presentation.api.schemas.master import WatchlistItemDTO


class GetWatchlistUseCase:
    """Use case to fetch all watchlist entries with resolved precision and maximum leverage tiers."""

    def __init__(self, watchlist_repo: IWatchlistRepository) -> None:
        self.watchlist_repo = watchlist_repo

    async def execute(self) -> List[WatchlistItemDTO]:
        """Fetch all watchlist entries with resolved precision and maximum leverage tiers."""
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
