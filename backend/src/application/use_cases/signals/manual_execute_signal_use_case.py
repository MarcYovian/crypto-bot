"""Use case for manually executing a trading signal from the dashboard."""

import uuid
from decimal import Decimal
from src.application.dto.trade_commands import ExecuteSignalCommand
from src.application.use_cases.trades.execute_signal_use_case import ExecuteSignalUseCase
from src.domain.entities.signal import ParsedSignalDTO
from src.domain.exceptions.signal import InvalidSignalDataError
from src.presentation.api.schemas.signal import (
    ManualSignalExecutionRequest,
    TradeExecutionResultResponseDTO,
)


class ManualExecuteSignalUseCase:
    """Validates manual signal inputs, enforces risk rules, and triggers execution orchestration."""

    def __init__(self, execute_signal_use_case: ExecuteSignalUseCase) -> None:
        self.execute_signal_use_case = execute_signal_use_case

    async def execute(
        self,
        payload: ManualSignalExecutionRequest,
        account_id: int = 1,
    ) -> TradeExecutionResultResponseDTO:
        """Validate manual signal inputs and execute trade via ExecuteSignalUseCase."""
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

        # 2. Build Domain ParsedSignalDTO
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

        # 3. Delegate to ExecuteSignalUseCase for risk management & order placement
        cmd = ExecuteSignalCommand(
            signal_dto=signal_dto,
            account_id=account_id,
            auto_tp_sl=payload.auto_tp_sl,
            is_manual=True,
        )
        exec_res = await self.execute_signal_use_case.execute(cmd)


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
