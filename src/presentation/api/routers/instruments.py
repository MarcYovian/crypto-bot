"""API Router for Binance Futures instruments metadata and on-demand synchronization."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from src.infrastructure.persistence.models.users import User
from src.presentation.api.schemas.master import InstrumentDTO, SyncInstrumentsResponseDTO
from src.application.use_cases.instruments import (
    ListInstrumentsUseCase,
    SyncInstrumentsUseCase,
)
from src.presentation.api.deps import (
    get_current_user,
    require_admin_role,
    get_list_instruments_use_case,
    get_sync_instruments_use_case,
    get_cache,
)
from src.utils.cache import AsyncInMemoryCache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/instruments", tags=["Watchlist & Instruments"])


@router.get(
    "",
    response_model=List[InstrumentDTO],
    summary="List all synced Binance Futures instruments",
    description="Retrieve all active Binance Futures contract specifications and leverage tier brackets.",
)
async def list_instruments(
    current_user: User = Depends(get_current_user),
    use_case: ListInstrumentsUseCase = Depends(get_list_instruments_use_case),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> List[InstrumentDTO]:
    """Retrieve all synchronized Binance Futures instruments (Cached with 30-minute TTL)."""
    cache_key = "instruments:all"
    cached = await cache.get(cache_key)
    if cached is not None:
        return [InstrumentDTO(**item) if isinstance(item, dict) else item for item in cached]

    items = await use_case.execute()
    # Cache for 30 minutes (1800 seconds)
    await cache.set(cache_key, [item.model_dump() for item in items], ttl_seconds=1800)
    return items


@router.post(
    "/sync",
    response_model=SyncInstrumentsResponseDTO,
    summary="Trigger manual sync of exchange metadata & leverage brackets",
    description="Fetch latest contract specifications and leverage brackets from Binance REST API and update local store.",
)
async def sync_instruments(
    current_user: User = Depends(require_admin_role),
    use_case: SyncInstrumentsUseCase = Depends(get_sync_instruments_use_case),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> SyncInstrumentsResponseDTO:
    """Trigger manual synchronization of instruments and leverage brackets from Binance."""
    try:
        result = await use_case.execute()

        # Invalidate cached instruments and watchlist entries
        await cache.invalidate("instruments")
        await cache.invalidate("watchlist")

        return result
    except Exception as e:
        logger.error(f"Failed to sync exchange instruments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to synchronize exchange instruments from Binance: {e}",
        )

