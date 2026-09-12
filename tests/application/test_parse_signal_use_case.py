"""Unit tests for ParseSignalUseCase."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.application.dto.signal_commands import ParseSignalCommand
from src.application.use_cases.signals.parse_signal_use_case import ParseSignalUseCase
from src.domain.events.signal_events import SignalReceivedEvent
from src.domain.ports.event_publisher import IDomainEventPublisher
from src.domain.ports.repositories import IInstrumentRepository, ISignalRepository
from src.domain.services.signal_parser import SignalParserDomainService


@pytest.mark.asyncio
async def test_parse_signal_use_case_success():
    signal_repo = MagicMock(spec=ISignalRepository)
    instrument_repo = MagicMock(spec=IInstrumentRepository)
    event_publisher = MagicMock(spec=IDomainEventPublisher)

    signal_repo.create = AsyncMock(return_value=MagicMock(id=42))
    instrument_repo.get_by_symbol = AsyncMock(return_value=MagicMock(id=1, symbol="BTCUSDT"))
    event_publisher.publish = AsyncMock()

    use_case = ParseSignalUseCase(
        signal_repo=signal_repo,
        instrument_repo=instrument_repo,
        event_publisher=event_publisher,
        parser=SignalParserDomainService(),
    )

    raw_text = """
    #BTC/USDT BUY LONG
    Entry: 65000 - 65200
    SL: 63000
    TP1: 67000
    TP2: 69000
    TP3: 71000
    Leverage: 10x
    """
    cmd = ParseSignalCommand(raw_text=raw_text, provider_id=1)
    result = await use_case.execute(cmd)

    assert result.is_valid is True
    assert result.symbol == "BTCUSDT"
    assert result.side == "BUY"
    assert result.sl_price == Decimal("63000")
    assert len(result.tp_targets) == 3

    signal_repo.create.assert_awaited_once()
    event_publisher.publish.assert_awaited_once()
    published_event = event_publisher.publish.call_args[0][0]
    assert isinstance(published_event, SignalReceivedEvent)
    assert published_event.signal_id == 42
    assert published_event.symbol == "BTCUSDT"
    assert published_event.tp_targets == [Decimal("67000"), Decimal("69000"), Decimal("71000")]


@pytest.mark.asyncio
async def test_parse_signal_use_case_invalid_text():
    signal_repo = MagicMock(spec=ISignalRepository)
    instrument_repo = MagicMock(spec=IInstrumentRepository)
    event_publisher = MagicMock(spec=IDomainEventPublisher)

    use_case = ParseSignalUseCase(
        signal_repo=signal_repo,
        instrument_repo=instrument_repo,
        event_publisher=event_publisher,
    )

    cmd = ParseSignalCommand(raw_text="Random chatter with no signal data")
    result = await use_case.execute(cmd)

    assert result.is_valid is False
    signal_repo.create.assert_not_called()
    event_publisher.publish.assert_not_called()
