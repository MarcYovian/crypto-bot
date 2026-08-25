"""API Router for Binance Futures instruments metadata and on-demand synchronization."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from src.database.models.users import User
from src.schemas.master import InstrumentDTO, SyncInstrumentsResponseDTO
from src.services.instrument_service import InstrumentService
from src.api.deps import get_current_user, require_admin_role, get_instrument_service, get_cache
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
    instrument_service: InstrumentService = Depends(get_instrument_service),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> List[InstrumentDTO]:
    """Retrieve all synchronized Binance Futures instruments (Cached with 30-minute TTL)."""
    cache_key = "instruments:all"
    cached = await cache.get(cache_key)
    if cached is not None:
        return [InstrumentDTO(**item) if isinstance(item, dict) else item for item in cached]

    items = await instrument_service.list_all_instruments()
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
    instrument_service: InstrumentService = Depends(get_instrument_service),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> SyncInstrumentsResponseDTO:
    """Trigger manual synchronization of instruments and leverage brackets from Binance."""
    try:
        result = await instrument_service.sync_exchange_instruments()

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
