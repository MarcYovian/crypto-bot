"""Use case for retrieving paginated signals feed."""

from typing import List, Optional
from src.domain.ports.repositories import ISignalRepository
from src.presentation.api.schemas.signal import PaginatedSignalListDTO, SignalItemDTO


class GetSignalsFeedUseCase:
    """Retrieves paginated trading signals feed with status filtering."""

    def __init__(self, signal_repo: ISignalRepository) -> None:
        self.signal_repo = signal_repo

    async def execute(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> PaginatedSignalListDTO:
        """Retrieve paginated signals feed."""
        total_count, raw_signals = await self.signal_repo.get_signals_paginated(
            page=page,
            page_size=page_size,
            status=status,
        )

        items: List[SignalItemDTO] = []
        for s in raw_signals:
            sym = s.instrument.symbol if getattr(s, "instrument", None) else "UNKNOWN"
            entry = float(s.entry_min) if s.entry_min else (float(s.entry_max) if s.entry_max else None)
            sl = float(s.sl_price) if s.sl_price else None
            tps = [float(tp) for tp in [s.tp1_price, s.tp2_price, s.tp3_price] if tp is not None]
            conf = float(s.confidence) if s.confidence is not None else 1.0

            items.append(
                SignalItemDTO(
                    id=s.id,
                    trace_id=f"sig-{s.id}",
                    raw_text=s.raw_message or "",
                    symbol=sym,
                    side=s.side.upper(),
                    entry_price=entry,
                    sl_price=sl,
                    tp_targets=tps,
                    confidence_score=conf,
                    status=s.status.upper(),
                    created_at=s.created_at,
                )
            )

        return PaginatedSignalListDTO(
            total=total_count,
            page=page,
            page_size=page_size,
            items=items,
        )
