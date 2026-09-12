"""Unit tests for persistence mappers (Domain <-> SQLAlchemy ORM)."""

import pytest
from decimal import Decimal
from datetime import datetime

from src.domain.aggregates.order_aggregate import OrderAggregate
from src.domain.aggregates.trade_aggregate import TradeAggregate
from src.domain.value_objects.side import MarginMode, OrderSide
from src.domain.value_objects.trade_status import OrderPurpose, OrderStatus, OrderType, TradeStatus
from src.infrastructure.persistence.mappers import OrderMapper, TradeMapper
from src.infrastructure.persistence.models.orders import Order
from src.infrastructure.persistence.models.trades import Trade


def test_order_mapper_to_domain_and_to_orm():
    orm_order = Order(
        id=10,
        trade_id=1,
        exchange_order_id="EX_101",
        client_order_id="CL_101",
        purpose="ENTRY",
        order_type="MARKET",
        side="BUY",
        price=Decimal("65000.0"),
        qty=Decimal("1.5"),
        filled_qty=Decimal("1.5"),
        status="FILLED",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
    )

    domain_order = OrderMapper.to_domain(orm_order)
    assert domain_order is not None
    assert domain_order.id == 10
    assert domain_order.trade_id == 1
    assert domain_order.exchange_order_id == "EX_101"
    assert domain_order.client_order_id == "CL_101"
    assert domain_order.side == OrderSide.BUY
    assert domain_order.order_type == OrderType.MARKET
    assert domain_order.purpose == OrderPurpose.ENTRY
    assert domain_order.status == OrderStatus.FILLED
    assert domain_order.quantity == Decimal("1.5")
    assert domain_order.filled_qty == Decimal("1.5")

    reconverted_orm = OrderMapper.to_orm(domain_order)
    assert reconverted_orm is not None
    assert reconverted_orm.id == 10
    assert reconverted_orm.trade_id == 1
    assert reconverted_orm.side == "BUY"
    assert reconverted_orm.purpose == "ENTRY"
    assert reconverted_orm.qty == Decimal("1.5")
    assert reconverted_orm.status == "FILLED"


def test_trade_mapper_to_domain_and_to_orm():
    orm_trade = Trade(
        id=1,
        account_id=1,
        instrument_id=2,
        strategy_id=3,
        signal_id=4,
        side="BUY",
        status="WAITING_ENTRY",
        entry_price=Decimal("65000.0"),
        sl_price=Decimal("64000.0"),
        tp1_price=Decimal("67000.0"),
        tp2_price=Decimal("69000.0"),
        tp3_price=Decimal("72000.0"),
        leverage=10,
        margin_mode="ISOLATED",
        position_size=Decimal("1.0"),
        remaining_qty=Decimal("1.0"),
        opened_at=None,
        closed_at=None,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
    )

    domain_trade = TradeMapper.to_domain(orm_trade)
    assert domain_trade is not None
    assert domain_trade.id == 1
    assert domain_trade.account_id == 1
    assert domain_trade.side == OrderSide.BUY
    assert domain_trade.status == TradeStatus.WAITING_ENTRY
    assert domain_trade.entry_price == Decimal("65000.0")
    assert domain_trade.sl_price == Decimal("64000.0")
    assert domain_trade.tp_targets == [Decimal("67000.0"), Decimal("69000.0"), Decimal("72000.0")]
    assert domain_trade.margin_mode == MarginMode.ISOLATED
    assert domain_trade.leverage == 10
    assert domain_trade.position_size == Decimal("1.0")

    reconverted_orm = TradeMapper.to_orm(domain_trade)
    assert reconverted_orm is not None
    assert reconverted_orm.id == 1
    assert reconverted_orm.account_id == 1
    assert reconverted_orm.side == "BUY"
    assert reconverted_orm.status == "WAITING_ENTRY"
    assert reconverted_orm.tp1_price == Decimal("67000.0")
    assert reconverted_orm.tp2_price == Decimal("69000.0")
    assert reconverted_orm.tp3_price == Decimal("72000.0")
