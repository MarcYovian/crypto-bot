"""Unit tests for CloseTradeUseCase."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.application.dto.trade_commands import CloseTradeCommand
from src.application.use_cases.trades.close_trade_use_case import CloseTradeUseCase
from src.domain.ports.event_publisher import IDomainEventPublisher
from src.domain.ports.gateways import IExchangeGateway
from src.domain.ports.repositories import (
    IOrderRepository,
    ITradeEventRepository,
    ITradeRepository,
    ITradeSummaryRepository,
)


@pytest.fixture
def mock_close_deps():
    trade_repo = MagicMock(spec=ITradeRepository)
    order_repo = MagicMock(spec=IOrderRepository)
    trade_event_repo = MagicMock(spec=ITradeEventRepository)
    trade_summary_repo = MagicMock(spec=ITradeSummaryRepository)
    exchange_gateway = MagicMock(spec=IExchangeGateway)
    event_publisher = MagicMock(spec=IDomainEventPublisher)

    trade_repo.get = AsyncMock()
    trade_repo.update_trade_status = AsyncMock()
    trade_repo.get_all_active_trades = AsyncMock()
    trade_event_repo.log_event = AsyncMock()
    trade_summary_repo.create = AsyncMock()
    exchange_gateway.cancel_all_open_orders = AsyncMock()
    exchange_gateway.create_order = AsyncMock()
    event_publisher.publish = AsyncMock()

    return {
        "trade_repo": trade_repo,
        "order_repo": order_repo,
        "trade_event_repo": trade_event_repo,
        "trade_summary_repo": trade_summary_repo,
        "exchange_gateway": exchange_gateway,
        "event_publisher": event_publisher,
    }


@pytest.mark.asyncio
async def test_close_trade_manual_success(mock_close_deps):
    mock_trade = MagicMock(
        id=101,
        status="OPEN",
        side="BUY",
        entry_price=Decimal("65000.0"),
        position_size=Decimal("0.5"),
        remaining_qty=Decimal("0.5"),
        instrument=MagicMock(symbol="BTCUSDT"),
    )
    mock_close_deps["trade_repo"].get.return_value = mock_trade
    mock_close_deps["exchange_gateway"].create_order.return_value = {
        "exchange_order_id": "CLOSE_EX_1",
        "average": Decimal("66000.0"),
    }

    use_case = CloseTradeUseCase(**mock_close_deps)

    result = await use_case.execute(CloseTradeCommand(trade_id=101, reason="MANUAL_CLOSE"))

    assert result["status"] == "CLOSED"
    assert result["trade_id"] == 101
    assert result["pnl"] == 500.0  # (66000 - 65000) * 0.5
    mock_close_deps["exchange_gateway"].cancel_all_open_orders.assert_awaited_once_with("BTCUSDT")
    mock_close_deps["event_publisher"].publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_panic_close_all(mock_close_deps):
    trade1 = MagicMock(id=101, status="OPEN", side="BUY", remaining_qty=Decimal("0.5"), entry_price=Decimal("65000"), instrument=MagicMock(symbol="BTCUSDT"))
    trade2 = MagicMock(id=102, status="OPEN", side="SELL", remaining_qty=Decimal("1.0"), entry_price=Decimal("3500"), instrument=MagicMock(symbol="ETHUSDT"))
    mock_close_deps["trade_repo"].get_all_active_trades.return_value = [trade1, trade2]
    mock_close_deps["trade_repo"].get.side_effect = lambda tid: trade1 if tid == 101 else trade2
    mock_close_deps["exchange_gateway"].create_order.return_value = {"average": Decimal("65000")}

    use_case = CloseTradeUseCase(**mock_close_deps)
    results = await use_case.panic_close_all(account_id=1)

    assert len(results) == 2
    assert results[0]["reason"] == "PANIC_CLOSE_ALL"
    assert results[1]["reason"] == "PANIC_CLOSE_ALL"
