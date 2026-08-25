"""API Router for Trading Strategies and Take Profit Scaling Rules."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from src.database.models.users import User
from src.schemas.master import StrategyDTO, StrategyUpdateRequest
from src.services.strategy_service import StrategyService
from src.domain.exceptions.provider import (
    StrategyNotFoundError,
    InvalidStrategyConfigError,
)
from src.api.deps import (
    get_current_user,
    require_admin_role,
    get_strategy_service,
    get_cache,
)
from src.utils.cache import AsyncInMemoryCache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/strategies", tags=["Strategies"])


@router.get(
    "",
    response_model=List[StrategyDTO],
    summary="List all trading strategies",
    description="Retrieve all configured trading strategies, TP allocation ratios, and trailing triggers.",
)
async def list_strategies(
    current_user: User = Depends(get_current_user),
    strategy_service: StrategyService = Depends(get_strategy_service),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> List[StrategyDTO]:
    """Retrieve all trading strategies with in-memory caching."""
    cache_key = "strategies:all"
    cached = await cache.get(cache_key)
    if cached is not None:
        return [StrategyDTO(**item) if isinstance(item, dict) else item for item in cached]

    items = await strategy_service.list_strategies()
    await cache.set(cache_key, [item.model_dump() for item in items])
    return items


@router.put(
    "/{id}",
    response_model=StrategyDTO,
    summary="Update strategy TP allocation ratios and trailing rules",
    description="Modify Take Profit stage allocation percentages (must total 100%) and trigger levels (Admin only).",
)
async def update_strategy(
    id: int,
    payload: StrategyUpdateRequest,
    current_user: User = Depends(require_admin_role),
    strategy_service: StrategyService = Depends(get_strategy_service),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> StrategyDTO:
    """Update TP allocation distributions and trailing/BEP triggers."""
    try:
        updated = await strategy_service.update_strategy(id, payload)
        # Write-through invalidation
        await cache.invalidate("strategies")
        return updated
    except StrategyNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidStrategyConfigError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to update strategy {id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error updating strategy: {e}",
        )
