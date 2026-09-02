"""Use case for extracting and persisting raw incoming trading signals."""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from src.application.dto.signal_commands import ParseSignalCommand
from src.domain.entities.signal import ParsedSignalDTO
from src.domain.events.signal_events import SignalReceivedEvent
from src.domain.ports.event_publisher import IDomainEventPublisher
from src.domain.ports.repositories import IInstrumentRepository, ISignalRepository
from src.domain.services.signal_parser import SignalParserDomainService
from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.symbol import Symbol
from src.domain.value_objects.trade_status import OrderType
from src.presentation.api.schemas import TradingSignalCreate

logger = logging.getLogger(__name__)


class ParseSignalUseCase:
    """Orchestrates parsing incoming raw text messages into structured signals and storing them."""

    def __init__(
        self,
        signal_repo: ISignalRepository,
        instrument_repo: IInstrumentRepository,
        event_publisher: Optional[IDomainEventPublisher] = None,
        parser: Optional[SignalParserDomainService] = None,
    ) -> None:
        self.signal_repo = signal_repo
        self.instrument_repo = instrument_repo
        self.event_publisher = event_publisher
        self.parser = parser or SignalParserDomainService()

    async def execute(self, cmd: ParseSignalCommand) -> ParsedSignalDTO:
        """Parse raw text, validate, persist, and publish event."""
        # 1. Parse raw text
        parsed_dto = self.parser.parse(cmd.raw_text)
        if not parsed_dto.is_valid:
            logger.debug("Signal parsing skipped/invalid: %s", parsed_dto.error_message)
            return parsed_dto

        clean_symbol = Symbol.normalize(parsed_dto.symbol)
        instrument = await self.instrument_repo.get_by_symbol(clean_symbol)

        # 2. Persist in database
        tp1 = parsed_dto.tp_targets[0] if len(parsed_dto.tp_targets) > 0 else None
        tp2 = parsed_dto.tp_targets[1] if len(parsed_dto.tp_targets) > 1 else None
        tp3 = parsed_dto.tp_targets[2] if len(parsed_dto.tp_targets) > 2 else None

        parsed_json_str = parsed_dto.model_dump_json() if hasattr(parsed_dto, "model_dump_json") else None

        signal_record = await self.signal_repo.create(
            TradingSignalCreate(
                provider_id=cmd.provider_id or 1,
                instrument_id=instrument.id if instrument else 1,
                side=parsed_dto.side.upper(),
                entry_min=parsed_dto.entry_min,
                entry_max=parsed_dto.entry_max,
                sl_price=parsed_dto.sl_price or Decimal("0"),
                tp1_price=tp1,
                tp2_price=tp2,
                tp3_price=tp3,
                timeframe=parsed_dto.timeframe,
                confidence=Decimal(str(parsed_dto.confidence_score)) if parsed_dto.confidence_score is not None else None,
                raw_message=cmd.raw_text,
                parsed_json=parsed_json_str,
                status="RECEIVED",
            )
        )


        # 3. Publish Domain Event
        if self.event_publisher:
            await self.event_publisher.publish(
                SignalReceivedEvent(
                    signal_id=signal_record.id,
                    provider_id=cmd.provider_id or 1,
                    symbol=clean_symbol,
                    side=OrderSide(parsed_dto.side.upper()),
                    order_type=OrderType(parsed_dto.order_type),
                    entry_min=parsed_dto.entry_min,
                    entry_max=parsed_dto.entry_max,
                    entry_targets=parsed_dto.entry_targets,
                    sl_price=parsed_dto.sl_price,
                    tp_targets=parsed_dto.tp_targets,
                    leverage=parsed_dto.leverage,
                    timeframe=parsed_dto.timeframe,
                    pattern=parsed_dto.pattern,
                    confidence_score=parsed_dto.confidence_score,
                    is_valid=parsed_dto.is_valid,
                    raw_text=cmd.raw_text,
                )
            )

        parsed_dto.id = signal_record.id
        return parsed_dto
