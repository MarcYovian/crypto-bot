"""Mapper between Trade ORM model and TradeAggregate domain aggregate."""

from decimal import Decimal
from typing import List, Optional

from src.domain.aggregates.trade_aggregate import TradeAggregate
from src.domain.value_objects.side import MarginMode, OrderSide
from src.domain.value_objects.trade_status import TradeStatus
from src.infrastructure.persistence.mappers.base_mapper import IMapper
from src.infrastructure.persistence.mappers.order_mapper import OrderMapper
from src.infrastructure.persistence.models.trades import Trade


class TradeMapper(IMapper[TradeAggregate, Trade]):
    """Bidirectional mapper between TradeAggregate and SQLAlchemy Trade ORM."""

    @classmethod
    def to_domain(cls, orm_entity: Optional[Trade]) -> Optional[TradeAggregate]:
        if orm_entity is None:
            return None

        symbol = getattr(orm_entity.instrument, "symbol", "") if hasattr(orm_entity, "instrument") and orm_entity.instrument else ""

        tp_targets: List[Decimal] = []
        for tp_col in (orm_entity.tp1_price, orm_entity.tp2_price, orm_entity.tp3_price):
            if tp_col is not None:
                tp_targets.append(Decimal(str(tp_col)))

        mapped_orders = []
        if hasattr(orm_entity, "orders") and orm_entity.orders:
            mapped_orders = [OrderMapper.to_domain(o) for o in orm_entity.orders if o is not None]

        return TradeAggregate(
            id=orm_entity.id,
            account_id=orm_entity.account_id,
            instrument_id=orm_entity.instrument_id,
            strategy_id=orm_entity.strategy_id,
            signal_id=orm_entity.signal_id,
            symbol=symbol,
            side=OrderSide.from_str(orm_entity.side),
            status=TradeStatus.from_str(orm_entity.status),
            entry_price=Decimal(str(orm_entity.entry_price or 0)),
            sl_price=Decimal(str(orm_entity.sl_price or 0)),
            position_size=Decimal(str(orm_entity.position_size or 0)),
            remaining_qty=Decimal(str(orm_entity.remaining_qty or 0)),
            leverage=orm_entity.leverage,
            margin_mode=MarginMode.from_str(orm_entity.margin_mode) if hasattr(orm_entity, "margin_mode") and orm_entity.margin_mode else MarginMode.ISOLATED,
            tp_targets=tp_targets,
            opened_at=orm_entity.opened_at,
            closed_at=orm_entity.closed_at,
            created_at=orm_entity.created_at,
            orders=mapped_orders,
        )

    @classmethod
    def to_orm(cls, domain_entity: Optional[TradeAggregate]) -> Optional[Trade]:
        if domain_entity is None:
            return None

        tp1 = domain_entity.tp_targets[0] if len(domain_entity.tp_targets) > 0 else None
        tp2 = domain_entity.tp_targets[1] if len(domain_entity.tp_targets) > 1 else None
        tp3 = domain_entity.tp_targets[2] if len(domain_entity.tp_targets) > 2 else None

        return Trade(
            id=domain_entity.id,
            account_id=domain_entity.account_id,
            instrument_id=domain_entity.instrument_id or 1,
            strategy_id=domain_entity.strategy_id,
            signal_id=domain_entity.signal_id,
            side=domain_entity.side.value if hasattr(domain_entity.side, "value") else str(domain_entity.side),
            status=domain_entity.status.value if hasattr(domain_entity.status, "value") else str(domain_entity.status),
            entry_price=domain_entity.entry_price,
            sl_price=domain_entity.sl_price,
            tp1_price=tp1,
            tp2_price=tp2,
            tp3_price=tp3,
            leverage=domain_entity.leverage,
            margin_mode=domain_entity.margin_mode.value if hasattr(domain_entity.margin_mode, "value") else str(domain_entity.margin_mode),
            position_size=domain_entity.position_size,
            remaining_qty=domain_entity.remaining_qty,
            opened_at=domain_entity.opened_at,
            closed_at=domain_entity.closed_at,
            created_at=domain_entity.created_at,
        )
