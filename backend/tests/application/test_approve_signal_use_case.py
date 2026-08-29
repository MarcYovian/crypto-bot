"""Unit tests for ApproveSignalUseCase."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.application.dto.signal_commands import ApproveSignalCommand
from src.application.dto.trade_commands import TradeExecutionResultDTO
from src.application.use_cases.signals.approve_signal_use_case import ApproveSignalUseCase
from src.application.use_cases.trades.execute_signal_use_case import ExecuteSignalUseCase
from src.domain.events.signal_events import SignalApprovedEvent
from src.domain.exceptions.signal import SignalNotFoundError
from src.domain.ports.event_publisher import IDomainEventPublisher
from src.domain.ports.repositories import ISignalRepository
from src.domain.value_objects.side import OrderSide


@pytest.mark.asyncio
async def test_approve_signal_use_case_success():
    signal_repo = MagicMock(spec=ISignalRepository)
    execute_signal_uc = MagicMock(spec=ExecuteSignalUseCase)
    event_publisher = MagicMock(spec=IDomainEventPublisher)

    mock_signal = MagicMock(
        id=10,
        side="BUY",
        entry_min=Decimal("65000"),
        entry_max=Decimal("65200"),
        sl_price=Decimal("63000"),
        tp1_price=Decimal("67000"),
        tp2_price=Decimal("69000"),
        tp3_price=Decimal("71000"),
        leverage=10,
        raw_message="BUY BTC",
        instrument=MagicMock(symbol="BTCUSDT"),
    )
    signal_repo.get = AsyncMock(return_value=mock_signal)
    signal_repo.update = AsyncMock()
    event_publisher.publish = AsyncMock()
    execute_signal_uc.execute = AsyncMock(
        return_value=TradeExecutionResultDTO(
            trade_id=100,
            symbol="BTCUSDT",
            side="BUY",
            status="OPEN",
            position_size=Decimal("0.5"),
            entry_price=Decimal("65000"),
            is_success=True,
            message="Trade executed",
        )
    )

    use_case = ApproveSignalUseCase(
        signal_repo=signal_repo,
        execute_signal_use_case=execute_signal_uc,
        event_publisher=event_publisher,
    )

    cmd = ApproveSignalCommand(signal_id=10, account_id=1)
    res = await use_case.execute(cmd)

    assert res.is_success is True
    assert res.trade_id == 100
    signal_repo.update.assert_awaited_once()
    event_publisher.publish.assert_awaited_once()

    pub_event = event_publisher.publish.call_args[0][0]
    assert isinstance(pub_event, SignalApprovedEvent)
    assert pub_event.signal_id == 10
    assert pub_event.symbol == "BTCUSDT"
    assert pub_event.side == OrderSide.BUY
    assert pub_event.entry_price == Decimal("65000")


@pytest.mark.asyncio
async def test_approve_signal_not_found():
    signal_repo = MagicMock(spec=ISignalRepository)
    execute_signal_uc = MagicMock(spec=ExecuteSignalUseCase)
    signal_repo.get = AsyncMock(return_value=None)

    use_case = ApproveSignalUseCase(
        signal_repo=signal_repo,
        execute_signal_use_case=execute_signal_uc,
    )

    cmd = ApproveSignalCommand(signal_id=999, account_id=1)
    with pytest.raises(SignalNotFoundError):
        await use_case.execute(cmd)
