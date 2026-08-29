"""API Router for Watchlist whitelist configuration and trading pair enablement."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from src.infrastructure.persistence.models.users import User
from src.presentation.api.schemas.master import WatchlistItemDTO, WatchlistToggleRequest
from src.application.use_cases.watchlist import (
    GetWatchlistUseCase,
    ToggleWatchlistUseCase,
)
from src.domain.exceptions.trade import SymbolNotWhitelistedError
from src.presentation.api.deps import (
    get_current_user,
    require_admin_role,
    get_watchlist_use_case,
    get_toggle_watchlist_use_case,
    get_cache,
)
from src.utils.cache import AsyncInMemoryCache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/watchlist", tags=["Watchlist & Instruments"])


@router.get(
    "",
    response_model=List[WatchlistItemDTO],
    summary="List all watchlist pairs",
    description="Retrieve all trading pairs in the whitelist with precision filters and max leverage.",
)
async def get_watchlist(
    current_user: User = Depends(get_current_user),
    use_case: GetWatchlistUseCase = Depends(get_watchlist_use_case),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> List[WatchlistItemDTO]:
    """Retrieve all whitelist pairs with in-memory caching."""
    cache_key = "watchlist:all"
    cached = await cache.get(cache_key)
    if cached is not None:
        return [WatchlistItemDTO(**item) if isinstance(item, dict) else item for item in cached]

    items = await use_case.execute()
    await cache.set(cache_key, [item.model_dump() for item in items])
    return items


@router.post(
    "/toggle",
    response_model=WatchlistItemDTO,
    summary="Enable or disable trading for a symbol",
    description="Toggle active trading status for a specific coin pair and invalidate relevant caches.",
)
async def toggle_watchlist_symbol(
    payload: WatchlistToggleRequest,
    current_user: User = Depends(require_admin_role),
    use_case: ToggleWatchlistUseCase = Depends(get_toggle_watchlist_use_case),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> WatchlistItemDTO:
    """Enable or disable trading for a symbol."""
    try:
        updated = await use_case.execute(
            symbol=payload.symbol,
            enabled=payload.enabled,
        )

        # Write-through invalidation
        await cache.invalidate("watchlist")
        await cache.invalidate("signals:feed")

        return updated
    except SymbolNotWhitelistedError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to toggle watchlist symbol {payload.symbol}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error toggling watchlist symbol: {e}",
        )

