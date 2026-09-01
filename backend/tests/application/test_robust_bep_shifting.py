"""Unit tests for robust in-place and fallback BEP shifting in HandleOrderFillUseCase."""

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

    trade_repo.update_partial_close = AsyncMock()
    trade_repo.update_trade_status = AsyncMock()
    trade_repo.update_sl_price = AsyncMock()
    trade_repo.update_stop_loss = AsyncMock()

    order_repo.get_orders_by_purpose = AsyncMock()
    order_repo.update = AsyncMock()
    order_repo.create = AsyncMock()

    trade_event_repo.log_event = AsyncMock()
    exchange_gateway.edit_order = AsyncMock()
    exchange_gateway.cancel_order = AsyncMock()
    exchange_gateway.cancel_stop_orders = AsyncMock()
    exchange_gateway.create_stop_loss_order = AsyncMock()
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
async def test_bep_shift_in_place_edit_success(mock_handler_deps):
    """When edit_order is supported, BEP shift edits order in-place without cancel/recreate."""
    deps = mock_handler_deps
    mock_sl_order = MagicMock(id=1, exchange_order_id="BIN_SL_100", trade_id=26)
    deps["order_repo"].get_orders_by_purpose.return_value = [mock_sl_order]
    deps["exchange_gateway"].edit_order.return_value = {"id": "BIN_SL_100", "status": "open"}

    mock_trade = MagicMock(
        id=26,
        account_id=1,
        side="SELL",
        entry_price=Decimal("48.54"),
        position_size=Decimal("855.912"),
        remaining_qty=Decimal("427.956"),
        sl_price=Decimal("48.60"),
        instrument=MagicMock(symbol="LTCUSDT"),
    )

    use_case = HandleOrderFillUseCase(**deps)
    await use_case._shift_stop_loss_to_bep(mock_trade)

    deps["exchange_gateway"].edit_order.assert_called_once()
    deps["trade_repo"].update_stop_loss.assert_called_with(26, Decimal("48.54"))
    deps["event_publisher"].publish.assert_called_once()


@pytest.mark.asyncio
async def test_bep_shift_fallback_cancel_stop_orders_on_edit_failure(mock_handler_deps):
    """When in-place edit fails, falls back to safe cancel_stop_orders and creates new BEP order."""
    deps = mock_handler_deps
    mock_sl_order = MagicMock(id=1, exchange_order_id="BIN_SL_100", trade_id=26)
    deps["order_repo"].get_orders_by_purpose.return_value = [mock_sl_order]
    deps["exchange_gateway"].edit_order.side_effect = Exception("Order modification not allowed")
    deps["exchange_gateway"].create_stop_loss_order.return_value = {"id": "NEW_BEP_SL_200"}

    mock_trade = MagicMock(
        id=26,
        account_id=1,
        side="SELL",
        entry_price=Decimal("48.54"),
        position_size=Decimal("855.912"),
        remaining_qty=Decimal("427.956"),
        sl_price=Decimal("48.60"),
        instrument=MagicMock(symbol="LTCUSDT"),
    )

    use_case = HandleOrderFillUseCase(**deps)
    await use_case._shift_stop_loss_to_bep(mock_trade)

    deps["exchange_gateway"].cancel_stop_orders.assert_called_with("LTCUSDT")
    deps["exchange_gateway"].create_stop_loss_order.assert_called_once()
    deps["trade_repo"].update_stop_loss.assert_called_with(26, Decimal("48.54"))
