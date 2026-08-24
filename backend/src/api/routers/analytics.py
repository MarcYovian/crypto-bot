"""FastAPI router for high-level analytics, dashboard summary, and equity growth metrics."""

from typing import List
from fastapi import APIRouter, Depends, Query

from src.api.deps import get_current_user, get_analytics_service, get_cache
from src.database.models.users import User
from src.schemas.analytics import AnalyticsSummaryDTO, EquityPointDTO
from src.services.analytics_service import AnalyticsService
from src.utils.cache import AsyncInMemoryCache

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("/summary", response_model=AnalyticsSummaryDTO, summary="Get high-level dashboard metrics")
async def get_analytics_summary(
    account_id: int = Query(default=1, ge=1, description="Trading Account ID"),
    current_user: User = Depends(get_current_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> AnalyticsSummaryDTO:
    """Retrieve summarized performance indicators, real-time balance, win rate, profit factor,

    and remaining daily risk budget for the dashboard.
    Cached for 10 seconds to avoid repeating heavy aggregate database queries.
    """
    cache_key = f"analytics:summary:{account_id}"
    cached_data = await cache.get(cache_key)
    if cached_data is not None:
        return AnalyticsSummaryDTO(**cached_data)

    response_dto = await analytics_service.get_dashboard_summary(account_id=account_id)

    # Save to Cache with 10s TTL
    await cache.set(cache_key, response_dto.model_dump(), ttl_seconds=10)

    return response_dto


@router.get("/equity-curve", response_model=List[EquityPointDTO], summary="Get equity growth curve chart data")
async def get_equity_curve(
    account_id: int = Query(default=1, ge=1, description="Trading Account ID"),
    timeframe: str = Query(default="30d", pattern="^(7d|30d|90d|all)$", description="Chart timeframe filter"),
    current_user: User = Depends(get_current_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> List[EquityPointDTO]:
    """Retrieve historical daily equity balance snapshots and realized PnL points for charting.

    Cached for 60 seconds per timeframe filter.
    """
    cache_key = f"analytics:equity:{account_id}:{timeframe}"
    cached_data = await cache.get(cache_key)
    if cached_data is not None:
        return [EquityPointDTO(**item) for item in cached_data]

    points = await analytics_service.get_equity_curve(account_id=account_id, timeframe=timeframe)

    # Save to Cache with 60s TTL
    await cache.set(cache_key, [p.model_dump(mode="json") for p in points], ttl_seconds=60)

    return points
