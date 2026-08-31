"""Use case for approving a signal and triggering order execution."""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from src.application.dto.signal_commands import ApproveSignalCommand
from src.application.dto.trade_commands import ExecuteSignalCommand, TradeExecutionResultDTO
from src.application.use_cases.trades.execute_signal_use_case import ExecuteSignalUseCase
from src.domain.events.signal_events import SignalApprovedEvent
from src.domain.exceptions import SignalNotFoundError
from src.domain.ports.event_publisher import IDomainEventPublisher
from src.domain.ports.repositories import ISignalRepository
from src.domain.value_objects.side import OrderSide
from src.domain.entities.signal import ParsedSignalDTO
from src.presentation.api.schemas import TradingSignalUpdate

logger = logging.getLogger(__name__)


class ApproveSignalUseCase:
    """Orchestrates operator signal approval and routes it into ExecuteSignalUseCase."""

    def __init__(
        self,
        signal_repo: ISignalRepository,
        execute_signal_use_case: ExecuteSignalUseCase,
        event_publisher: Optional[IDomainEventPublisher] = None,
    ) -> None:
        self.signal_repo = signal_repo
        self.execute_signal_uc = execute_signal_use_case
        self.event_publisher = event_publisher

    async def execute(self, cmd: ApproveSignalCommand) -> TradeExecutionResultDTO:
        """Approve signal and immediately execute trade."""
        signal = await self.signal_repo.get(cmd.signal_id)
        if not signal:
            raise SignalNotFoundError(f"Signal #{cmd.signal_id} not found.")

        # 1. Update status in database
        await self.signal_repo.update(signal, TradingSignalUpdate(confirmation_status="APPROVED"))

        # 2. Build ParsedSignalDTO
        sym = signal.instrument.symbol if signal.instrument else "BTCUSDT"
        tps = [tp for tp in [signal.tp1_price, signal.tp2_price, signal.tp3_price] if tp is not None]

        sig_dto = ParsedSignalDTO(
            symbol=sym,
            side=signal.side.upper(),
            entry_min=signal.entry_min or Decimal("0"),
            entry_max=signal.entry_max or Decimal("0"),
            sl_price=signal.sl_price or Decimal("0"),
            tp_targets=tps,
            leverage=cmd.custom_leverage or getattr(signal, "leverage", None) or 10,
            is_valid=True,
            raw_text=signal.raw_message or "",
        )


        # 3. Publish Approval Domain Event
        if self.event_publisher:
            await self.event_publisher.publish(
                SignalApprovedEvent(
                    signal_id=signal.id,
                    symbol=sym,
                    side=OrderSide(signal.side.upper()),
                    approved_by=f"ACCOUNT_{cmd.account_id}",
                    entry_price=sig_dto.entry_min,
                    sl_price=sig_dto.sl_price,
                    leverage=sig_dto.leverage,
                )
            )

        # 4. Trigger Execution
        return await self.execute_signal_uc.execute(
            ExecuteSignalCommand(
                signal_dto=sig_dto,
                account_id=cmd.account_id,
                signal_id=signal.id,
            )
        )
