"""API Router for Signal Providers and Performance Leaderboard."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from src.infrastructure.persistence.models.users import User
from src.presentation.api.schemas.master import (
    SignalProviderDTO,
    SignalProviderCreateRequest,
    ProviderPerformanceDTO,
)
from src.application.use_cases.providers import (
    ListProvidersUseCase,
    CreateProviderUseCase,
    GetProviderPerformanceUseCase,
)
from src.domain.exceptions.provider import (
    ProviderNotFoundError,
    DuplicateProviderError,
)
from src.presentation.api.deps import (
    get_current_user,
    require_admin_role,
    get_list_providers_use_case,
    get_create_provider_use_case,
    get_provider_performance_use_case,
    get_cache,
)
from src.utils.cache import AsyncInMemoryCache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/providers", tags=["Signal Providers"])


@router.get(
    "",
    response_model=List[SignalProviderDTO],
    summary="List all configured signal channels",
    description="Retrieve all configured Telegram signal channels and webhook sources.",
)
async def list_providers(
    current_user: User = Depends(get_current_user),
    use_case: ListProvidersUseCase = Depends(get_list_providers_use_case),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> List[SignalProviderDTO]:
    """Retrieve all signal provider channels with in-memory caching."""
    cache_key = "providers:all"
    cached = await cache.get(cache_key)
    if cached is not None:
        return [SignalProviderDTO(**item) if isinstance(item, dict) else item for item in cached]

    items = await use_case.execute()
    await cache.set(cache_key, [item.model_dump() for item in items])
    return items


@router.post(
    "",
    response_model=SignalProviderDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new Telegram signal provider channel",
    description="Register a new Telegram channel or webhook signal source (Admin only).",
)
async def create_provider(
    payload: SignalProviderCreateRequest,
    current_user: User = Depends(require_admin_role),
    use_case: CreateProviderUseCase = Depends(get_create_provider_use_case),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> SignalProviderDTO:
    """Register a new signal provider channel."""
    try:
        new_provider = await use_case.execute(payload)
        # Write-through invalidation
        await cache.invalidate("providers")
        return new_provider
    except DuplicateProviderError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to create provider '{payload.name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error creating signal provider: {e}",
        )


@router.get(
    "/{id}/analytics",
    response_model=ProviderPerformanceDTO,
    summary="Get performance metrics for a specific signal provider",
    description="Retrieve win rate, executed trades count, and realized net PnL for a provider (Cached 30s).",
)
async def get_provider_analytics(
    id: int,
    current_user: User = Depends(get_current_user),
    use_case: GetProviderPerformanceUseCase = Depends(get_provider_performance_use_case),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> ProviderPerformanceDTO:
    """Retrieve financial performance statistics for a specific provider."""
    cache_key = f"providers:analytics:{id}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return ProviderPerformanceDTO(**cached) if isinstance(cached, dict) else cached

    try:
        performance = await use_case.execute(id)
        await cache.set(cache_key, performance.model_dump(), ttl_seconds=30)
        return performance
    except ProviderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to fetch performance for provider {id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error fetching provider analytics: {e}",
        )

