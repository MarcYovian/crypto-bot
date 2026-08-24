"""FastAPI router for Active Positions, Trade History, Deep Nested Details, and Manual Close operations."""

from datetime import datetime, time, date, timezone
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Path, HTTPException, status
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db_session, get_cache
from src.database.models import (
    Trade,
    Instrument,
    TradeRisk,
    Order,
    Execution,
    TradeEvent,
    TradeSummary,
    User,
)
from src.schemas.trade import (
    ActiveTradeDTO,
    ActiveTradeTPLevelDTO,
    TradeHistoryItemDTO,
    PaginatedTradeHistoryDTO,
    TradeDetailDTO,
    TradeRiskDetailDTO,
    TradeOrderDetailDTO,
    TradeExecutionDetailDTO,
    TradeEventDetailDTO,
    TradeSummaryDetailDTO,
    CloseTradeRequest,
)
from src.schemas.common import GenericActionResponse
from src.repository.trade_repository import TradeRepository
from src.repository.order_repository import OrderRepository
from src.repository.execution_repository import ExecutionRepository
from src.repository.trade_event_repository import TradeEventRepository
from src.repository.trade_summary_repository import TradeSummaryRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.services.position_manager import PositionManager
from src.utils.cache import AsyncInMemoryCache

router = APIRouter(prefix="/api/v1/trades", tags=["Trades"])


@router.get("/active", response_model=List[ActiveTradeDTO], summary="List all active open positions")
async def get_active_trades(
    account_id: int = Query(default=1, ge=1, description="Trading Account ID"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> List[ActiveTradeDTO]:
    """Retrieve all open, partially filled, or waiting entry positions with live unrealized PnL and TP status."""
    stmt = (
        select(Trade)
        .options(
            selectinload(Trade.instrument),
            selectinload(Trade.events),
            selectinload(Trade.orders),
        )
        .where(
            Trade.account_id == account_id,
            Trade.status.in_(["WAITING_ENTRY", "OPEN", "PARTIAL"]),
        )
        .order_by(Trade.created_at.desc())
    )
    result = await session.execute(stmt)
    trades: List[Trade] = list(result.scalars().all())

    items: List[ActiveTradeDTO] = []
    for t in trades:
        symbol = t.instrument.symbol if t.instrument else "UNKNOWN"
        entry_price = float(t.entry_price) if t.entry_price else None
        sl_price = float(t.sl_price) if t.sl_price else None
        pos_size = float(t.position_size)
        rem_qty = float(t.remaining_qty)
        leverage = int(t.leverage) if t.leverage else 20

        # Attempt to get live market price from cache; fallback to entry price or SL
        cached_price = await cache.get(f"ticker:{symbol}")
        current_price = float(cached_price) if cached_price is not None else entry_price

        # Calculate live unrealized PnL and ROI %
        unrealized_pnl = 0.0
        unrealized_pnl_percent = 0.0
        if t.status in ("OPEN", "PARTIAL") and entry_price and current_price and rem_qty > 0:
            if t.side.upper() == "BUY":
                price_diff = current_price - entry_price
            else:
                price_diff = entry_price - current_price
            unrealized_pnl = round(price_diff * rem_qty, 2)
            pos_margin = (entry_price * rem_qty) / leverage if leverage > 0 else 1.0
            unrealized_pnl_percent = round((unrealized_pnl / pos_margin) * 100, 2)

        # Map TP levels and hit status from events
        hit_event_types = {e.event_type for e in t.events}
        tp_levels: List[ActiveTradeTPLevelDTO] = []
        if t.tp1_price:
            tp_levels.append(
                ActiveTradeTPLevelDTO(
                    level=1,
                    price=float(t.tp1_price),
                    is_hit="TP1_HIT" in hit_event_types,
                )
            )
        if t.tp2_price:
            tp_levels.append(
                ActiveTradeTPLevelDTO(
                    level=2,
                    price=float(t.tp2_price),
                    is_hit="TP2_HIT" in hit_event_types,
                )
            )
        if t.tp3_price:
            tp_levels.append(
                ActiveTradeTPLevelDTO(
                    level=3,
                    price=float(t.tp3_price),
                    is_hit="TP3_HIT" in hit_event_types,
                )
            )

        items.append(
            ActiveTradeDTO(
                trade_id=t.id,
                symbol=symbol,
                side=t.side.upper(),
                status=t.status.upper(),
                entry_price=entry_price,
                current_price=current_price,
                sl_price=sl_price,
                position_size=pos_size,
                remaining_qty=rem_qty,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_percent=unrealized_pnl_percent,
                leverage=leverage,
                margin_mode=t.margin_mode.upper(),
                tp_levels=tp_levels,
                opened_at=t.opened_at,
            )
        )

    return items


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
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedTradeHistoryDTO:
    """Retrieve paginated historical closed and cancelled trades with filtering by symbol, outcome, and date range."""
    # Base query joined with instrument and summary
    stmt = (
        select(Trade)
        .options(
            selectinload(Trade.instrument),
            selectinload(Trade.summary),
        )
        .where(
            Trade.account_id == account_id,
            Trade.status.in_(["CLOSED", "CANCELLED"]),
        )
    )

    count_stmt = select(func.count(Trade.id)).where(
        Trade.account_id == account_id,
        Trade.status.in_(["CLOSED", "CANCELLED"]),
    )

    if symbol:
        clean_symbol = symbol.strip().upper()
        stmt = stmt.join(Trade.instrument).where(Instrument.symbol == clean_symbol)
        count_stmt = count_stmt.join(Trade.instrument).where(Instrument.symbol == clean_symbol)

    if result:
        clean_result = result.strip().upper()
        if clean_result == "CANCELLED":
            stmt = stmt.where(Trade.status == "CANCELLED")
            count_stmt = count_stmt.where(Trade.status == "CANCELLED")
        else:
            stmt = stmt.join(Trade.summary).where(TradeSummary.result == clean_result)
            count_stmt = count_stmt.join(Trade.summary).where(TradeSummary.result == clean_result)

    if start_date:
        start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        stmt = stmt.where(Trade.created_at >= start_dt)
        count_stmt = count_stmt.where(Trade.created_at >= start_dt)

    if end_date:
        end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
        stmt = stmt.where(Trade.created_at <= end_dt)
        count_stmt = count_stmt.where(Trade.created_at <= end_dt)

    # Count total
    total_res = await session.execute(count_stmt)
    total_count: int = total_res.scalar_one() or 0

    # Paginate
    offset = (page - 1) * page_size
    stmt = stmt.order_by(Trade.closed_at.desc().nullslast(), Trade.created_at.desc()).offset(offset).limit(page_size)
    trades_res = await session.execute(stmt)
    trades = list(trades_res.scalars().all())

    items: List[TradeHistoryItemDTO] = []
    for t in trades:
        sym = t.instrument.symbol if t.instrument else "UNKNOWN"
        summary = t.summary

        # Outcome determination
        trade_result = summary.result if summary else ("CANCELLED" if t.status == "CANCELLED" else "CLOSED")
        net_pnl = float(summary.net_pnl) if summary else None
        roi_percent = float(summary.roi) if summary else None
        close_reason = summary.close_reason if summary else None

        items.append(
            TradeHistoryItemDTO(
                id=t.id,
                symbol=sym,
                side=t.side.upper(),
                entry_price=float(t.entry_price) if t.entry_price else None,
                exit_price=float(t.avg_entry_price) if t.avg_entry_price else None,
                position_size=float(t.position_size),
                net_pnl=net_pnl,
                roi_percent=roi_percent,
                result=trade_result,
                close_reason=close_reason,
                opened_at=t.opened_at,
                closed_at=t.closed_at,
            )
        )

    return PaginatedTradeHistoryDTO(
        total=total_count,
        page=page,
        page_size=page_size,
        items=items,
    )


@router.get("/{id}", response_model=TradeDetailDTO, summary="Get full trade detail")
async def get_trade_detail(
    id: int = Path(..., ge=1, description="Trade Primary Key ID"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> TradeDetailDTO:
    """Fetch deep trade details with all 5 child relationships: risk, orders, executions, events, and summary."""
    trade_repo = TradeRepository(session)
    trade = await trade_repo.get_detail(id)
    if not trade:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade with ID {id} was not found.",
        )

    symbol = trade.instrument.symbol if getattr(trade, "instrument", None) else "UNKNOWN"

    # 1. Risk details
    risk_dto: Optional[TradeRiskDetailDTO] = None
    if trade.trade_risk:
        risk_dto = TradeRiskDetailDTO(
            risk_amount_usdt=float(trade.trade_risk.risk_amount),
            stop_distance=float(trade.trade_risk.stop_distance),
            required_margin=float(trade.trade_risk.margin),
        )

    # 2. Orders
    orders_dto = [
        TradeOrderDetailDTO(
            id=o.id,
            exchange_order_id=o.exchange_order_id,
            purpose=o.purpose,
            order_type=o.order_type,
            side=o.side,
            price=float(o.price) if o.price else None,
            qty=float(o.qty),
            status=o.status,
        )
        for o in trade.orders
    ]

    # 3. Executions
    execs_dto = [
        TradeExecutionDetailDTO(
            price=float(e.price),
            qty=float(e.qty),
            commission=float(e.commission),
            realized_pnl=float(e.realized_pnl),
            executed_at=e.executed_at,
        )
        for e in trade.executions
    ]

    # 4. Events
    events_dto = [
        TradeEventDetailDTO(
            event_type=ev.event_type,
            payload=ev.payload_json,
            created_at=ev.created_at,
        )
        for ev in trade.events
    ]

    # 5. Summary
    summary_dto: Optional[TradeSummaryDetailDTO] = None
    if trade.summary:
        summary_dto = TradeSummaryDetailDTO(
            gross_pnl=float(trade.summary.gross_pnl),
            net_pnl=float(trade.summary.net_pnl),
            commission=float(trade.summary.commission),
            roi=float(trade.summary.roi),
            result=trade.summary.result,
        )

    return TradeDetailDTO(
        trade_id=trade.id,
        symbol=symbol,
        side=trade.side.upper(),
        status=trade.status.upper(),
        entry_price=float(trade.entry_price) if trade.entry_price else None,
        sl_price=float(trade.sl_price) if trade.sl_price else None,
        position_size=float(trade.position_size),
        leverage=int(trade.leverage) if trade.leverage else 20,
        risk_details=risk_dto,
        orders=orders_dto,
        executions=execs_dto,
        events=events_dto,
        summary=summary_dto,
    )


@router.post("/{id}/close", response_model=GenericActionResponse, summary="Emergency/manual position close")
async def manual_close_trade(
    id: int = Path(..., ge=1, description="Trade Primary Key ID"),
    payload: CloseTradeRequest = CloseTradeRequest(),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> GenericActionResponse:
    """Manually close an open position by submitting an immediate market order to Binance and finalizing trade record."""
    trade_repo = TradeRepository(session)
    order_repo = OrderRepository(session)
    exec_repo = ExecutionRepository(session)
    event_repo = TradeEventRepository(session)
    summary_repo = TradeSummaryRepository(session)
    daily_risk_repo = DailyRiskRepository(session)

    trade = await trade_repo.get(id)
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

    pos_manager = PositionManager(
        trade_repo=trade_repo,
        order_repo=order_repo,
        execution_repo=exec_repo,
        trade_event_repo=event_repo,
        trade_summary_repo=summary_repo,
        daily_risk_repo=daily_risk_repo,
    )

    success = await pos_manager.close_position_market(trade_id=id, reason=payload.reason)
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
