"""FastAPI router for Active Positions, Trade History, Deep Nested Details, and Manual Close operations."""

from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Path, HTTPException, status

from src.presentation.api.deps import (
    get_current_user,
    get_active_trades_use_case,
    get_trade_history_use_case,
    get_trade_detail_use_case,
    get_close_trade_use_case,
    get_cache,
)
from src.infrastructure.persistence.models import User
from src.domain.exceptions.trade import (
    TradeNotFoundError,
    InvalidTradeStateError,
    TradeExecutionError,
)
from src.application.dto.trade_commands import CloseTradeCommand
from src.application.use_cases.trades import (
    GetActiveTradesUseCase,
    GetTradeHistoryUseCase,
    GetTradeDetailUseCase,
    CloseTradeUseCase,
)
from src.presentation.api.schemas.trade import (
    ActiveTradeDTO,
    PaginatedTradeHistoryDTO,
    TradeDetailDTO,
    CloseTradeRequest,
)
from src.presentation.api.schemas.common import GenericActionResponse
from src.utils.cache import AsyncInMemoryCache

router = APIRouter(prefix="/api/v1/trades", tags=["Trades"])


@router.get("/active", response_model=List[ActiveTradeDTO], summary="List all active open positions")
async def get_active_trades(
    account_id: int = Query(default=1, ge=1, description="Trading Account ID"),
    current_user: User = Depends(get_current_user),
    use_case: GetActiveTradesUseCase = Depends(get_active_trades_use_case),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> List[ActiveTradeDTO]:
    """Retrieve all open, partially filled, or waiting entry positions with live unrealized PnL and TP status."""
    raw_cached = await cache.get_by_prefix("ticker:")
    cached_prices: dict[str, float] = {
        k.split(":", 1)[1]: float(v) for k, v in raw_cached.items() if v is not None
    }

    return await use_case.execute(account_id=account_id, live_prices=cached_prices)


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
    use_case: GetTradeHistoryUseCase = Depends(get_trade_history_use_case),
) -> PaginatedTradeHistoryDTO:
    """Retrieve paginated historical closed and cancelled trades with filtering by symbol, outcome, and date range."""
    return await use_case.execute(
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
    use_case: GetTradeDetailUseCase = Depends(get_trade_detail_use_case),
) -> TradeDetailDTO:
    """Fetch deep trade details with all 5 child relationships: risk, orders, executions, events, and summary."""
    try:
        return await use_case.execute(trade_id=id)
    except TradeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post("/{id}/close", response_model=GenericActionResponse, summary="Emergency/manual position close")
async def manual_close_trade(
    id: int = Path(..., ge=1, description="Trade Primary Key ID"),
    payload: CloseTradeRequest = CloseTradeRequest(),
    current_user: User = Depends(get_current_user),
    use_case: CloseTradeUseCase = Depends(get_close_trade_use_case),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> GenericActionResponse:
    """Manually close an open position by submitting an immediate market order to Binance and finalizing trade record."""
    try:
        cmd = CloseTradeCommand(trade_id=id, reason=payload.reason)
        await use_case.execute(cmd)
    except TradeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidTradeStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except TradeExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    # Invalidate dashboard summary and equity caches
    await cache.invalidate("analytics:summary")
    await cache.invalidate("analytics:equity")

    return GenericActionResponse(
        success=True,
        message=f"Position for trade #{id} has been closed successfully via market order ({payload.reason}).",
    )

