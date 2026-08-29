"""Mapper between Order ORM model and OrderAggregate domain entity."""

from decimal import Decimal
from typing import Optional

from src.domain.aggregates.order_aggregate import OrderAggregate
from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.trade_status import OrderPurpose, OrderStatus, OrderType
from src.infrastructure.persistence.mappers.base_mapper import IMapper
from src.infrastructure.persistence.models.orders import Order


class OrderMapper(IMapper[OrderAggregate, Order]):
    """Bidirectional mapper between OrderAggregate and SQLAlchemy Order ORM."""

    @classmethod
    def to_domain(cls, orm_entity: Optional[Order]) -> Optional[OrderAggregate]:
        if orm_entity is None:
            return None

        symbol = getattr(orm_entity.trade, "symbol", "") if hasattr(orm_entity, "trade") and orm_entity.trade else ""

        return OrderAggregate(
            id=orm_entity.id,
            trade_id=orm_entity.trade_id,
            symbol=symbol,
            side=OrderSide.from_str(orm_entity.side),
            order_type=OrderType.from_str(orm_entity.order_type),
            purpose=OrderPurpose.from_str(orm_entity.purpose),
            quantity=Decimal(str(orm_entity.qty or 0)),
            price=Decimal(str(orm_entity.price)) if orm_entity.price is not None else None,
            exchange_order_id=orm_entity.exchange_order_id,
            client_order_id=orm_entity.client_order_id,
            filled_qty=Decimal(str(orm_entity.filled_qty or 0)),
            status=OrderStatus.from_str(orm_entity.status),
            created_at=orm_entity.created_at,
        )

    @classmethod
    def to_orm(cls, domain_entity: Optional[OrderAggregate]) -> Optional[Order]:
        if domain_entity is None:
            return None

        return Order(
            id=domain_entity.id,
            trade_id=domain_entity.trade_id,
            exchange_order_id=domain_entity.exchange_order_id,
            client_order_id=domain_entity.client_order_id,
            purpose=domain_entity.purpose.value if hasattr(domain_entity.purpose, "value") else str(domain_entity.purpose),
            order_type=domain_entity.order_type.value if hasattr(domain_entity.order_type, "value") else str(domain_entity.order_type),
            side=domain_entity.side.value if hasattr(domain_entity.side, "value") else str(domain_entity.side),
            price=domain_entity.price,
            qty=domain_entity.quantity,
            filled_qty=domain_entity.filled_qty,
            status=domain_entity.status.value if hasattr(domain_entity.status, "value") else str(domain_entity.status),
            created_at=domain_entity.created_at,
        )
