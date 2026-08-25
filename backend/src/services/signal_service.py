"""Signal orchestration and feed management domain service."""

import uuid
from decimal import Decimal
from typing import Optional, List

from src.domain.entities.signal import ParsedSignalDTO
from src.domain.exceptions.signal import InvalidSignalDataError
from src.repository.signal_repository import SignalRepository
from src.repository.instrument_repository import InstrumentRepository
from src.schemas.signal import (
    SignalItemDTO,
    PaginatedSignalListDTO,
    ManualSignalExecutionRequest,
    TradeExecutionResultResponseDTO,
)
from src.services.trade_service import TradeService


class SignalService:
    """Service handling signal feed querying, manual execution validation, and orchestration."""

    def __init__(
        self,
        signal_repo: SignalRepository,
        trade_service: TradeService,
        instrument_repo: Optional[InstrumentRepository] = None,
    ) -> None:
        self.signal_repo = signal_repo
        self.trade_service = trade_service
        self.instrument_repo = instrument_repo

    async def get_signals_feed(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> PaginatedSignalListDTO:
        """Retrieve paginated signals feed.

        Args:
            page: Current page number.
            page_size: Records per page.
            status: Optional lifecycle or OpenAPI status filter.

        Returns:
            PaginatedSignalListDTO containing list of SignalItemDTO.
        """
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

    async def manual_execute_signal(
        self,
        payload: ManualSignalExecutionRequest,
        account_id: int = 1,
    ) -> TradeExecutionResultResponseDTO:
        """Validate manual signal inputs, enforce risk, and trigger trade orchestration.

        Args:
            payload: Manual signal request parameters.
            account_id: Target trading account ID.

        Returns:
            TradeExecutionResultResponseDTO with execution feedback.

        Raises:
            InvalidSignalDataError: If price boundaries violate BUY/SELL geometry.
        """
        clean_symbol = payload.symbol.strip().upper()
        clean_side = payload.side.strip().upper()

        # 1. Price Geometry Validations
        if clean_side == "BUY":
            if payload.sl_price >= payload.entry_price:
                raise InvalidSignalDataError(
                    f"For BUY signal, Stop Loss ({payload.sl_price}) must be lower than Entry Price ({payload.entry_price})."
                )
            for tp in payload.tp_targets:
                if tp <= payload.entry_price:
                    raise InvalidSignalDataError(
                        f"For BUY signal, Take Profit ({tp}) must be higher than Entry Price ({payload.entry_price})."
                    )
        elif clean_side == "SELL":
            if payload.sl_price <= payload.entry_price:
                raise InvalidSignalDataError(
                    f"For SELL signal, Stop Loss ({payload.sl_price}) must be higher than Entry Price ({payload.entry_price})."
                )
            for tp in payload.tp_targets:
                if tp >= payload.entry_price:
                    raise InvalidSignalDataError(
                        f"For SELL signal, Take Profit ({tp}) must be lower than Entry Price ({payload.entry_price})."
                    )

        # 2. Convert to Domain ParsedSignalDTO
        entry_dec = Decimal(str(payload.entry_price))
        sl_dec = Decimal(str(payload.sl_price))
        tp_decimals = [Decimal(str(tp)) for tp in payload.tp_targets]
        trace_id = f"manual-exec-{uuid.uuid4().hex[:8]}"

        signal_dto = ParsedSignalDTO(
            raw_text=f"MANUAL_DASHBOARD: {clean_side} {clean_symbol} @ {payload.entry_price} SL: {payload.sl_price} TPs: {payload.tp_targets}",
            symbol=clean_symbol,
            side=clean_side,
            order_type="LIMIT",
            entry_min=entry_dec,
            entry_max=entry_dec,
            entry_targets=[entry_dec],
            sl_price=sl_dec,
            tp_targets=tp_decimals,
            leverage=payload.leverage,
            confidence_score=1.0,
            is_valid=True,
            trace_id=trace_id,
        )

        # 3. Delegate to TradeService for Risk Management (2%) & Exchange Placement
        exec_res = await self.trade_service.execute_signal(
            signal_dto=signal_dto,
            account_id=account_id,
            auto_tp_sl=payload.auto_tp_sl,
        )

        return TradeExecutionResultResponseDTO(
            is_success=exec_res.is_success,
            trade_id=exec_res.trade_id,
            symbol=exec_res.symbol,
            side=exec_res.side,
            position_size=float(exec_res.position_size),
            leverage=payload.leverage,
            entry_order_id=exec_res.entry_order_id,
            sl_order_id=exec_res.sl_order_id,
            tp_order_ids=exec_res.tp_order_ids,
            message=exec_res.message,
        )
