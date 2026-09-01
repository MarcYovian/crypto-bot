"""Use case for rejecting an incoming signal."""

import logging
from typing import Any, Dict, Optional

from src.application.dto.signal_commands import RejectSignalCommand
from src.domain.events.signal_events import SignalRejectedEvent
from src.domain.exceptions import SignalNotFoundError
from src.domain.ports.event_publisher import IDomainEventPublisher
from src.domain.ports.repositories import ISignalRepository
from src.domain.value_objects.side import OrderSide
from src.presentation.api.schemas import TradingSignalUpdate

logger = logging.getLogger(__name__)


class RejectSignalUseCase:
    """Orchestrates marking a signal as rejected."""

    def __init__(
        self,
        signal_repo: ISignalRepository,
        event_publisher: Optional[IDomainEventPublisher] = None,
    ) -> None:
        self.signal_repo = signal_repo
        self.event_publisher = event_publisher

    async def execute(self, cmd: RejectSignalCommand) -> Dict[str, Any]:
        """Reject signal by ID."""
        signal = await self.signal_repo.get(cmd.signal_id)
        if not signal:
            raise SignalNotFoundError(f"Signal #{cmd.signal_id} not found.")

        await self.signal_repo.update(signal, TradingSignalUpdate(status="REJECTED"))

        sym = signal.instrument.symbol if signal.instrument else "UNKNOWN"
        if self.event_publisher:
            await self.event_publisher.publish(
                SignalRejectedEvent(
                    signal_id=signal.id,
                    symbol=sym,
                    side=OrderSide(signal.side.upper()) if signal.side else OrderSide.BUY,
                    rejected_by=f"ACCOUNT_{cmd.account_id}",
                    reason=cmd.reason,
                )
            )

        return {"signal_id": signal.id, "status": "REJECTED", "reason": cmd.reason}
