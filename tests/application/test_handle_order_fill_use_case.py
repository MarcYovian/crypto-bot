"""Unit tests for HandleOrderFillUseCase state transitions."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.application.dto.trade_commands import OrderFillPayload
from src.application.use_cases.trades.handle_order_fill_use_case import HandleOrderFillUseCase
from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.trade_status import OrderStatus, OrderType
from src.domain.ports.event_publisher import IDomainEventPublisher
from src.domain.ports.gateways import IExchangeGateway
from src.domain.ports.repositories import (
    IDailyRiskRepository,
    IExecutionRepository,
    IInstrumentRepository,
    IOrderRepository,
    ITradeEventRepository,
    ITradeRepository,
    ITradeRiskRepository,
    ITradeSummaryRepository,
)


@pytest.fixture
def mock_fill_deps():
    trade_repo = MagicMock(spec=ITradeRepository)
    order_repo = MagicMock(spec=IOrderRepository)
    execution_repo = MagicMock(spec=IExecutionRepository)
    trade_event_repo = MagicMock(spec=ITradeEventRepository)
    trade_risk_repo = MagicMock(spec=ITradeRiskRepository)
    trade_summary_repo = MagicMock(spec=ITradeSummaryRepository)
    daily_risk_repo = MagicMock(spec=IDailyRiskRepository)
    instrument_repo = MagicMock(spec=IInstrumentRepository)
    exchange_gateway = MagicMock(spec=IExchangeGateway)
    event_publisher = MagicMock(spec=IDomainEventPublisher)

    trade_repo.get = AsyncMock()
    trade_repo.update_entry_fill = AsyncMock()
    trade_repo.update_partial_close = AsyncMock()
    trade_repo.update_trade_status = AsyncMock()
    trade_repo.update_stop_loss = AsyncMock()
    order_repo.get_by_client_order_id = AsyncMock()
    order_repo.get_orders_by_purpose = AsyncMock(return_value=[])
    order_repo.update = AsyncMock()
    order_repo.create = AsyncMock()
    execution_repo.create = AsyncMock()
    trade_event_repo.log_event = AsyncMock()
    trade_risk_repo.create = AsyncMock()
    trade_summary_repo.create = AsyncMock()
    daily_risk_repo.get_by_account_id = AsyncMock()
    instrument_repo.get = AsyncMock()
    exchange_gateway.create_order = AsyncMock(return_value={"exchange_order_id": "BEP_ORDER_999"})
    exchange_gateway.create_stop_loss_order = AsyncMock(return_value={"exchange_order_id": "BEP_ORDER_999"})
    exchange_gateway.cancel_order = AsyncMock(return_value={"status": "CANCELED"})
    exchange_gateway.cancel_all_open_orders = AsyncMock()
    event_publisher.publish = AsyncMock()

    return {
        "trade_repo": trade_repo,
        "order_repo": order_repo,
        "execution_repo": execution_repo,
        "trade_event_repo": trade_event_repo,
        "trade_risk_repo": trade_risk_repo,
        "trade_summary_repo": trade_summary_repo,
        "daily_risk_repo": daily_risk_repo,
        "instrument_repo": instrument_repo,
        "exchange_gateway": exchange_gateway,
        "event_publisher": event_publisher,
    }


@pytest.mark.asyncio
async def test_handle_tp1_fill_shifts_sl_to_bep(mock_fill_deps):
    # Mock Order for TP1
    mock_order = MagicMock(
        id=201,
        trade_id=101,
        purpose="TP1",
        qty=Decimal("0.5"),
    )
    mock_fill_deps["order_repo"].get_by_client_order_id.return_value = mock_order

    # Mock Trade with remaining qty 1.0
    mock_trade = MagicMock(
        id=101,
        account_id=1,
        status="OPEN",
        side="BUY",
        entry_price=Decimal("65000.0"),
        position_size=Decimal("1.0"),
        remaining_qty=Decimal("1.0"),
        sl_price=Decimal("63000.0"),
        instrument=MagicMock(symbol="BTCUSDT"),
    )
    mock_fill_deps["trade_repo"].get.return_value = mock_trade
    mock_fill_deps["exchange_gateway"].create_order.return_value = {"exchange_order_id": "BEP_ORDER_999"}

    use_case = HandleOrderFillUseCase(**mock_fill_deps)

    payload = OrderFillPayload(
        symbol="BTCUSDT",
        exchange_order_id="TP1_EX_101",
        client_order_id="TP1_101",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        status=OrderStatus.FILLED,
        fill_price=Decimal("67000.0"),
        fill_qty=Decimal("0.5"),
        cumulative_filled_qty=Decimal("0.5"),
    )

    result = await use_case.execute(payload)

    assert result["status"] == "TP_FILLED"
    assert result["tp_tier"] == "TP1"
    # Verify partial close updated with remaining 0.5
    mock_fill_deps["trade_repo"].update_partial_close.assert_awaited_once_with(
        trade_id=101,
        closed_qty=Decimal("0.5"),
        remaining_qty=Decimal("0.5"),
        realized_pnl=Decimal("1000.0"),  # (67000 - 65000) * 0.5
    )
    # Verify Stop Loss updated to BEP (65000.0)
    mock_fill_deps["trade_repo"].update_stop_loss.assert_awaited_once_with(101, Decimal("65000.0"))
    mock_fill_deps["event_publisher"].publish.assert_awaited()


@pytest.mark.asyncio
async def test_handle_order_fill_from_raw_event(mock_fill_deps):
    use_case = HandleOrderFillUseCase(**mock_fill_deps)

    tp_order = MagicMock()
    tp_order.id = 55
    tp_order.trade_id = 101
    tp_order.side = "SELL"
    tp_order.purpose = "TP1"
    tp_order.qty = Decimal("0.5")
    tp_order.price = Decimal("67000.0")
    tp_order.client_order_id = "TP1_101"

    mock_fill_deps["order_repo"].get_by_exchange_order_id = AsyncMock(return_value=tp_order)
    mock_fill_deps["order_repo"].get_by_client_order_id = AsyncMock(return_value=tp_order)

    trade = MagicMock()
    trade.id = 101
    trade.account_id = 1
    trade.symbol = "BTCUSDT"
    trade.side = "BUY"
    trade.entry_price = Decimal("65000.0")
    trade.position_size = Decimal("1.0")
    trade.remaining_qty = Decimal("1.0")
    trade.sl_price = Decimal("64000.0")
    trade.leverage = 10
    trade.status = "OPEN"

    mock_fill_deps["trade_repo"].get.return_value = trade

    raw_event = {
        "id": "BINANCE_999",
        "clientOrderId": "TP1_101",
        "status": "FILLED",
        "symbol": "BTC/USDT:USDT",
        "filled": "0.5",
        "average": "67000.0",
        "fee": {"cost": "0.2"},
    }

    result = await use_case.execute_from_raw_event(raw_event)
    assert result is not None
    assert result["status"] == "TP_FILLED"
    mock_fill_deps["order_repo"].get_by_exchange_order_id.assert_awaited_with("BINANCE_999")

