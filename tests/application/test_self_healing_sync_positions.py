"""Unit tests for self-healing position reconciliation in SyncPositionsUseCase."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.application.dto.trade_commands import SyncPositionsCommand
from src.application.use_cases.trades.sync_positions_use_case import SyncPositionsUseCase
from src.domain.ports.event_publisher import IDomainEventPublisher
from src.domain.ports.gateways import IExchangeGateway
from src.domain.ports.repositories import (
    IExecutionRepository,
    IInstrumentRepository,
    IOrderRepository,
    ITradeRepository,
    ITradeSummaryRepository,
)


@pytest.fixture
def mock_sync_deps():
    trade_repo = MagicMock(spec=ITradeRepository)
    instrument_repo = MagicMock(spec=IInstrumentRepository)
    exchange_gateway = MagicMock(spec=IExchangeGateway)
    order_repo = MagicMock(spec=IOrderRepository)
    execution_repo = MagicMock(spec=IExecutionRepository)
    trade_summary_repo = MagicMock(spec=ITradeSummaryRepository)
    event_publisher = MagicMock(spec=IDomainEventPublisher)

    trade_repo.get_active_trades_with_instrument = AsyncMock()
    trade_repo.get_all_active_trades = AsyncMock()
    trade_repo.update_partial_close = AsyncMock()
    trade_repo.update_trade_status = AsyncMock()

    order_repo.cancel_all_open_orders_for_trade = AsyncMock()
    execution_repo.create = AsyncMock()
    trade_summary_repo.get = AsyncMock(return_value=None)
    trade_summary_repo.create = AsyncMock()
    trade_summary_repo.update = AsyncMock()

    exchange_gateway.fetch_positions = AsyncMock()
    exchange_gateway.fetch_my_trades = AsyncMock()
    exchange_gateway.cancel_all_open_orders = AsyncMock()
    event_publisher.publish = AsyncMock()

    return {
        "trade_repo": trade_repo,
        "instrument_repo": instrument_repo,
        "exchange_gateway": exchange_gateway,
        "order_repo": order_repo,
        "execution_repo": execution_repo,
        "trade_summary_repo": trade_summary_repo,
        "event_publisher": event_publisher,
    }


@pytest.mark.asyncio
async def test_self_healing_reconciliation_fetches_real_exit_and_publishes_event(mock_sync_deps):
    """When a trade is closed on Binance while bot was offline, sync self-heals by fetching trades and publishing event."""
    deps = mock_sync_deps
    # 1. Binance returns 0 contracts for XRPUSDT
    deps["exchange_gateway"].fetch_positions.return_value = []

    # 2. Binance returns real exit trade history
    deps["exchange_gateway"].fetch_my_trades.return_value = [
        {
            "id": "154766486",
            "order": "3491504613",
            "symbol": "XRP/USDT:USDT",
            "side": "sell",
            "price": "1.3699",
            "amount": "16309.6",
            "fee": {"cost": "8.937", "currency": "USDT"},
        }
    ]

    # 3. Active Trade in DB
    mock_trade = MagicMock(
        id=23,
        account_id=1,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("1.3755"),
        sl_price=Decimal("1.3700"),
        position_size=Decimal("16309.6"),
        remaining_qty=Decimal("16309.6"),
        instrument=MagicMock(symbol="XRPUSDT"),
    )
    deps["trade_repo"].get_active_trades_with_instrument.return_value = [mock_trade]

    use_case = SyncPositionsUseCase(**deps)
    cmd = SyncPositionsCommand(account_id=1)
    res = await use_case.execute(cmd)

    assert res["status"] == "COMPLETED"
    assert res["desynced_trades"] == 1
    assert res["details"][0]["action"] == "SELF_HEALED_CLOSED"
    assert res["details"][0]["reason"] == "STOP_LOSS_HIT"

    # Verify execution was recorded
    deps["execution_repo"].create.assert_called_once()
    # Verify trade status updated to CLOSED
    deps["trade_repo"].update_trade_status.assert_called_once()
    # Verify trade summary was created
    deps["trade_summary_repo"].create.assert_called_once()
    # Verify TradeClosedEvent published (triggering Telegram report)
    deps["event_publisher"].publish.assert_called_once()
