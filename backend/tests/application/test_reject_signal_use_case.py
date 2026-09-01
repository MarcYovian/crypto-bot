"""Unit tests for RejectSignalUseCase."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.dto.signal_commands import RejectSignalCommand
from src.application.use_cases.signals.reject_signal_use_case import RejectSignalUseCase
from src.domain.events.signal_events import SignalRejectedEvent
from src.domain.exceptions.signal import SignalNotFoundError
from src.domain.ports.event_publisher import IDomainEventPublisher
from src.domain.ports.repositories import ISignalRepository
from src.domain.value_objects.side import OrderSide


@pytest.mark.asyncio
async def test_reject_signal_use_case_success():
    signal_repo = MagicMock(spec=ISignalRepository)
    event_publisher = MagicMock(spec=IDomainEventPublisher)

    mock_signal = MagicMock(
        id=25,
        side="BUY",
        instrument=MagicMock(symbol="ETHUSDT"),
    )
    signal_repo.get = AsyncMock(return_value=mock_signal)
    signal_repo.update = AsyncMock()
    event_publisher.publish = AsyncMock()

    use_case = RejectSignalUseCase(
        signal_repo=signal_repo,
        event_publisher=event_publisher,
    )

    cmd = RejectSignalCommand(signal_id=25, account_id=1, reason="Market too volatile")
    res = await use_case.execute(cmd)

    assert res["signal_id"] == 25
    assert res["status"] == "REJECTED"
    assert res["reason"] == "Market too volatile"

    signal_repo.update.assert_awaited_once()
    event_publisher.publish.assert_awaited_once()

    pub_event = event_publisher.publish.call_args[0][0]
    assert isinstance(pub_event, SignalRejectedEvent)
    assert pub_event.signal_id == 25
    assert pub_event.symbol == "ETHUSDT"
    assert pub_event.side == OrderSide.BUY
    assert pub_event.reason == "Market too volatile"


@pytest.mark.asyncio
async def test_reject_signal_not_found():
    signal_repo = MagicMock(spec=ISignalRepository)
    signal_repo.get = AsyncMock(return_value=None)

    use_case = RejectSignalUseCase(signal_repo=signal_repo)

    cmd = RejectSignalCommand(signal_id=999, account_id=1)
    with pytest.raises(SignalNotFoundError):
        await use_case.execute(cmd)
