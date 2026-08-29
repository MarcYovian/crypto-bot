"""Tests for PlaceBracketOrdersUseCase."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.application.dto.trade_commands import PlaceBracketOrdersCommand
from src.application.use_cases.trades.place_bracket_orders_use_case import PlaceBracketOrdersUseCase
from src.domain.ports.gateways import IExchangeGateway
from src.domain.ports.repositories import IOrderRepository, ITradeRepository



@pytest.mark.asyncio
async def test_place_bracket_orders_success():
    order_repo = AsyncMock(spec=IOrderRepository)
    exchange_gw = AsyncMock(spec=IExchangeGateway)
    trade_repo = AsyncMock(spec=ITradeRepository)

    exchange_gw.create_stop_loss_order = AsyncMock(return_value={"id": "EXCH_SL_101"})
    exchange_gw.create_take_profit_order = AsyncMock(return_value={"id": "EXCH_TP_101"})

    use_case = PlaceBracketOrdersUseCase(
        order_repo=order_repo,
        exchange_gateway=exchange_gw,
        trade_repo=trade_repo,
    )

    cmd = PlaceBracketOrdersCommand(
        trade_id=1,
        symbol="BTCUSDT",
        side="BUY",
        position_size=Decimal("0.5"),
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("62000"), Decimal("64000")],
        auto_tp_sl=True,
    )

    res = await use_case.execute(cmd)

    assert res.success is True
    assert res.sl_order_id == "EXCH_SL_101"
    assert len(res.tp_order_ids) == 2
    assert res.tp_order_ids[0] == "EXCH_TP_101"
    assert order_repo.create.call_count == 3  # 1 SL + 2 TP orders


@pytest.mark.asyncio
async def test_place_bracket_orders_disabled():
    order_repo = AsyncMock(spec=IOrderRepository)
    use_case = PlaceBracketOrdersUseCase(order_repo=order_repo)

    cmd = PlaceBracketOrdersCommand(
        trade_id=1,
        symbol="BTCUSDT",
        side="BUY",
        position_size=Decimal("0.5"),
        auto_tp_sl=False,
    )

    res = await use_case.execute(cmd)

    assert res.success is True
    assert res.sl_order_id is None
    assert len(res.tp_order_ids) == 0
    assert order_repo.create.call_count == 0
