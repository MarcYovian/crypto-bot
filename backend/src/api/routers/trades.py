"""FastAPI router for Active Positions, Trade History, Deep Nested Details, and Manual Close operations."""

from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Path, HTTPException, status

from src.api.deps import (
    get_current_user,
    get_trade_service,
    get_position_manager,
    get_cache,
)
from src.database.models import User
from src.schemas.trade import (
    ActiveTradeDTO,
    PaginatedTradeHistoryDTO,
    TradeDetailDTO,
    CloseTradeRequest,
)
from src.schemas.common import GenericActionResponse
from src.services.trade_service import TradeService
from src.services.position_manager import PositionManager
from src.utils.cache import AsyncInMemoryCache

router = APIRouter(prefix="/api/v1/trades", tags=["Trades"])


@router.get("/active", response_model=List[ActiveTradeDTO], summary="List all active open positions")
async def get_active_trades(
    account_id: int = Query(default=1, ge=1, description="Trading Account ID"),
    current_user: User = Depends(get_current_user),
    trade_service: TradeService = Depends(get_trade_service),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> List[ActiveTradeDTO]:
    """Retrieve all open, partially filled, or waiting entry positions with live unrealized PnL and TP status."""
    raw_cached = await cache.get_by_prefix("ticker:")
    cached_prices: dict[str, float] = {
        k.split(":", 1)[1]: float(v) for k, v in raw_cached.items() if v is not None
    }

    return await trade_service.get_active_positions(account_id=account_id, live_prices=cached_prices)


@router.get("/history", response_model=PaginatedTradeHistoryDTO, summary="List trade history")
async def get_trade_history(
    account_id: int = Query(default=1, ge=1, description="Trading Account ID"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    symbol: Optional[str] = Query(default=None, description="Filter by trading pair symbol"),
    result: Optional[str] = Query(default=None, pattern="^(WIN|LOSS|BREAKEVEN|CANCELLED)$", description="Filter outcome"),
    start_date: Optional[date] = Query(default=None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(default=None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    trade_service: TradeService = Depends(get_trade_service),
) -> PaginatedTradeHistoryDTO:
    """Retrieve paginated historical closed and cancelled trades with filtering by symbol, outcome, and date range."""
    return await trade_service.get_trade_history(
        account_id=account_id,
        page=page,
        page_size=page_size,
        symbol=symbol,
        result=result,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/{id}", response_model=TradeDetailDTO, summary="Get full trade detail")
async def get_trade_detail(
    id: int = Path(..., ge=1, description="Trade Primary Key ID"),
    current_user: User = Depends(get_current_user),
    trade_service: TradeService = Depends(get_trade_service),
) -> TradeDetailDTO:
    """Fetch deep trade details with all 5 child relationships: risk, orders, executions, events, and summary."""
    trade_detail = await trade_service.get_trade_detail(trade_id=id)
    if not trade_detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade with ID {id} was not found.",
        )
    return trade_detail


@router.post("/{id}/close", response_model=GenericActionResponse, summary="Emergency/manual position close")
async def manual_close_trade(
    id: int = Path(..., ge=1, description="Trade Primary Key ID"),
    payload: CloseTradeRequest = CloseTradeRequest(),
    current_user: User = Depends(get_current_user),
    trade_service: TradeService = Depends(get_trade_service),
    position_manager: PositionManager = Depends(get_position_manager),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> GenericActionResponse:
    """Manually close an open position by submitting an immediate market order to Binance and finalizing trade record."""
    trade = await trade_service.trade_repo.get(id)
    if not trade:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade with ID {id} was not found.",
        )

    if trade.status in ("CLOSED", "CANCELLED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trade #{id} cannot be closed because it is already {trade.status}.",
        )

    success = await position_manager.close_position_market(trade_id=id, reason=payload.reason)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute manual market closure for trade #{id}.",
        )

    # Invalidate dashboard summary and equity caches
    await cache.invalidate("analytics:summary")
    await cache.invalidate("analytics:equity")

    return GenericActionResponse(
        success=True,
        message=f"Position for trade #{id} has been closed successfully via market order ({payload.reason}).",
    )
