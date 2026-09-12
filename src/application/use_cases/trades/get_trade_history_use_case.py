"""Use case for querying historical closed and cancelled trades with pagination and filters."""

from datetime import datetime, time as dt_time, timezone
from typing import Any, List, Optional
from src.domain.ports.repositories import ITradeRepository
from src.presentation.api.schemas.trade import (
    PaginatedTradeHistoryDTO,
    TradeHistoryItemDTO,
)


class GetTradeHistoryUseCase:
    """Retrieves paginated trade history filtered by account, symbol, result, and date range."""

    def __init__(self, trade_repo: ITradeRepository) -> None:
        self.trade_repo = trade_repo

    async def execute(
        self,
        account_id: int = 1,
        page: int = 1,
        page_size: int = 20,
        symbol: Optional[str] = None,
        result: Optional[str] = None,
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None,
    ) -> PaginatedTradeHistoryDTO:
        """Fetch filtered and paginated trade history."""
        start_dt = None
        if start_date:
            if isinstance(start_date, datetime):
                start_dt = start_date
            else:
                start_dt = datetime.combine(start_date, dt_time.min, tzinfo=timezone.utc)

        end_dt = None
        if end_date:
            if isinstance(end_date, datetime):
                end_dt = end_date
            else:
                end_dt = datetime.combine(end_date, dt_time.max, tzinfo=timezone.utc)

        total_count, trades = await self.trade_repo.get_history_paginated(
            account_id=account_id,
            page=page,
            page_size=page_size,
            symbol=symbol,
            result=result,
            start_date=start_dt,
            end_date=end_dt,
        )

        items: List[TradeHistoryItemDTO] = []
        for t in trades:
            sym = t.instrument.symbol if getattr(t, "instrument", None) else "UNKNOWN"
            summary = getattr(t, "summary", None)
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
                    exit_price=float(t.avg_entry_price) if getattr(t, "avg_entry_price", None) else None,
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
