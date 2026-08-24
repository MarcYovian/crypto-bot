"""FastAPI router for Telegram Signals feed and manual UI signal execution."""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status

from src.api.deps import (
    get_current_user,
    get_signal_service,
    get_cache,
)
from src.database.models import User
from src.domain.exceptions.signal import (
    InvalidSignalDataError,
    SignalParseError,
)
from src.domain.exceptions.trade import (
    TradeExecutionError,
    PairAlreadyActiveError,
    SymbolNotWhitelistedError,
    DailyRiskLimitReachedError,
)
from src.domain.exceptions.risk import MaxRiskExceededError
from src.schemas.signal import (
    PaginatedSignalListDTO,
    ManualSignalExecutionRequest,
    TradeExecutionResultResponseDTO,
)
from src.services.signal_service import SignalService
from src.utils.cache import AsyncInMemoryCache

router = APIRouter(prefix="/api/v1/signals", tags=["Signals"])


@router.get("", response_model=PaginatedSignalListDTO, summary="List incoming Telegram signals feed")
async def get_signals_feed(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(default=None, description="Filter signal status (e.g. RECEIVED, EXECUTED, PENDING, PROCESSED)"),
    account_id: int = Query(default=1, ge=1, description="Trading Account ID"),
    current_user: User = Depends(get_current_user),
    signal_service: SignalService = Depends(get_signal_service),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> PaginatedSignalListDTO:
    """Retrieve paginated list of Telegram signals with status filtering and 5-second caching."""
    cache_key = f"signals:feed:{account_id}:{page}:{page_size}:{status}"
    cached_data = await cache.get(cache_key)
    if cached_data is not None:
        return PaginatedSignalListDTO(**cached_data)

    feed_dto = await signal_service.get_signals_feed(
        page=page,
        page_size=page_size,
        status=status,
    )

    await cache.set(cache_key, feed_dto.model_dump(mode="json"), ttl_seconds=5)
    return feed_dto


@router.post("/manual-execute", response_model=TradeExecutionResultResponseDTO, summary="Manually execute a trading signal")
async def manual_execute_signal(
    payload: ManualSignalExecutionRequest,
    account_id: int = Query(default=1, ge=1, description="Trading Account ID"),
    current_user: User = Depends(get_current_user),
    signal_service: SignalService = Depends(get_signal_service),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> TradeExecutionResultResponseDTO:
    """Validate manual signal parameters, apply 2.0% max account risk budget, and execute trade on exchange."""
    try:
        result = await signal_service.manual_execute_signal(
            payload=payload,
            account_id=account_id,
        )
    except (InvalidSignalDataError, SignalParseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid signal parameter: {exc}",
        ) from exc
    except SymbolNotWhitelistedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Symbol rejected: {exc}",
        ) from exc
    except PairAlreadyActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Pair already active: {exc}",
        ) from exc
    except (DailyRiskLimitReachedError, MaxRiskExceededError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Risk limit breach: {exc}",
        ) from exc
    except TradeExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Trade execution failed: {exc}",
        ) from exc

    # Invalidate feed and dashboard caches
    await cache.invalidate("signals:feed")
    await cache.invalidate("analytics:summary")
    await cache.invalidate("analytics:equity")
    await cache.invalidate("trades:active")

    return result
