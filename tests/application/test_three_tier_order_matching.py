"""Unit tests for 3-Tier Order Matching in HandleOrderFillUseCase."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.application.use_cases.trades.handle_order_fill_use_case import HandleOrderFillUseCase
from src.domain.ports.event_publisher import IDomainEventPublisher
from src.domain.ports.gateways import IExchangeGateway
from src.domain.ports.repositories import (
    IDailyRiskRepository,
    IExecutionRepository,
    IOrderRepository,
    ITradeEventRepository,
    ITradeRepository,
    ITradeRiskRepository,
    ITradeSummaryRepository,
)
from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.trade_status import OrderPurpose


@pytest.fixture
def mock_handler_deps():
    trade_repo = MagicMock(spec=ITradeRepository)
    order_repo = MagicMock(spec=IOrderRepository)
    execution_repo = MagicMock(spec=IExecutionRepository)
    trade_event_repo = MagicMock(spec=ITradeEventRepository)
    trade_summary_repo = MagicMock(spec=ITradeSummaryRepository)
    trade_risk_repo = MagicMock(spec=ITradeRiskRepository)
    daily_risk_repo = MagicMock(spec=IDailyRiskRepository)
    exchange_gateway = MagicMock(spec=IExchangeGateway)
    event_publisher = MagicMock(spec=IDomainEventPublisher)

    trade_repo.get = AsyncMock()
    trade_repo.update_partial_close = AsyncMock()
    trade_repo.update_trade_status = AsyncMock()
    trade_repo.get_all_active_trades = AsyncMock()

    order_repo.get_by_exchange_order_id = AsyncMock()
    order_repo.get_by_client_order_id = AsyncMock()
    order_repo.get_orders_by_purpose = AsyncMock()
    order_repo.create = AsyncMock()
    order_repo.cancel_all_open_orders_for_trade = AsyncMock()

    execution_repo.create = AsyncMock()
    execution_repo.get_total_commission_by_trade = AsyncMock(return_value=Decimal("0.0"))
    execution_repo.get_executions_by_trade_id = AsyncMock(return_value=[])

    trade_event_repo.log_event = AsyncMock()
    trade_summary_repo.get = AsyncMock(return_value=None)
    trade_summary_repo.create = AsyncMock()
    trade_summary_repo.update = AsyncMock()

    exchange_gateway.cancel_all_open_orders = AsyncMock()
    event_publisher.publish = AsyncMock()

    return {
        "trade_repo": trade_repo,
        "order_repo": order_repo,
        "execution_repo": execution_repo,
        "trade_event_repo": trade_event_repo,
        "trade_summary_repo": trade_summary_repo,
        "trade_risk_repo": trade_risk_repo,
        "daily_risk_repo": daily_risk_repo,
        "exchange_gateway": exchange_gateway,
        "event_publisher": event_publisher,
    }


@pytest.mark.asyncio
async def test_tier_1_exact_exchange_order_id_match(mock_handler_deps):
    """Tier 1 match: Order is found directly by exchange_order_id."""
    deps = mock_handler_deps
    mock_order = MagicMock(id=1, trade_id=10, side=OrderSide.SELL, purpose="TP1", client_order_id="TP1_10", price=Decimal("100"), qty=Decimal("1.0"))
    deps["order_repo"].get_by_exchange_order_id.return_value = mock_order
    deps["order_repo"].get_by_client_order_id.return_value = mock_order
    deps["order_repo"].get.return_value = mock_order

    mock_trade = MagicMock(id=10, account_id=1, side="BUY", status="OPEN", position_size=Decimal("2.0"), remaining_qty=Decimal("2.0"), entry_price=Decimal("90.0"), instrument=MagicMock(symbol="BTCUSDT"))
    deps["trade_repo"].get.return_value = mock_trade

    use_case = HandleOrderFillUseCase(**deps)

    raw_event = {
        "id": "BIN_EXACT_123",
        "symbol": "BTC/USDT:USDT",
        "status": "FILLED",
        "filled": "1.0",
        "average": "100.0",
    }

    res = await use_case.execute_from_raw_event(raw_event)
    assert res is not None
    assert res.get("status") == "TP_FILLED"
    deps["order_repo"].get_by_exchange_order_id.assert_called_with("BIN_EXACT_123")


@pytest.mark.asyncio
async def test_tier_3_contextual_match_for_triggered_sl(mock_handler_deps):
    """Tier 3 match: Triggered SL generates new untracked order ID, matches active trade context."""
    deps = mock_handler_deps
    # Tier 1 & 2 return None
    deps["order_repo"].get_by_exchange_order_id.return_value = None
    deps["order_repo"].get_by_client_order_id.return_value = None

    mock_trade = MagicMock(
        id=23,
        account_id=1,
        side="BUY",
        status="OPEN",
        position_size=Decimal("1000.0"),
        remaining_qty=Decimal("1000.0"),
        entry_price=Decimal("1.3755"),
        sl_price=Decimal("1.3700"),
        tp1_price=Decimal("1.4000"),
        tp2_price=Decimal("1.4250"),
        tp3_price=Decimal("1.4500"),
        instrument=MagicMock(symbol="XRPUSDT"),
    )
    deps["trade_repo"].get_all_active_trades.return_value = [mock_trade]
    deps["trade_repo"].get.return_value = mock_trade

    mock_sl_order = MagicMock(id=84, trade_id=23, side=OrderSide.SELL, purpose="SL", client_order_id="SL_23", price=Decimal("1.3700"), qty=Decimal("1000.0"))
    deps["order_repo"].get_orders_by_purpose.return_value = [mock_sl_order]
    deps["order_repo"].get.return_value = mock_sl_order

    use_case = HandleOrderFillUseCase(**deps)

    # Raw order update generated by Binance with fresh market execution ID 3491504613
    raw_event = {
        "id": "3491504613",
        "clientOrderId": "autoclose-3491504613",
        "symbol": "XRP/USDT:USDT",
        "side": "sell",
        "status": "FILLED",
        "filled": "1000.0",
        "average": "1.3699",
    }

    res = await use_case.execute_from_raw_event(raw_event)
    assert res is not None
    assert res.get("status") == "SL_FILLED"
    assert res.get("trade_id") == 23
    deps["trade_repo"].update_trade_status.assert_called_once()
    deps["event_publisher"].publish.assert_called_once()
