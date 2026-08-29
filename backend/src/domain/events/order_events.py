"""Domain events related to exchange order execution."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Union
from src.domain.events.base import DomainEvent
from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.trade_status import OrderStatus, OrderPurpose, OrderType


@dataclass(frozen=True, kw_only=True)
class OrderCreatedEvent(DomainEvent):
    """Fired when an order is created and submitted to exchange."""

    order_id: int
    trade_id: int
    symbol: str
    side: OrderSide
    order_type: OrderType
    purpose: OrderPurpose
    price: Optional[Decimal]
    qty: Decimal
    client_order_id: str
    exchange_order_id: Optional[str] = None
    reduce_only: bool = False
    time_in_force: Optional[str] = "GTC"

    def __post_init__(self) -> None:
        if not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide.from_str(self.side))
        if not isinstance(self.order_type, OrderType):
            object.__setattr__(self, "order_type", OrderType.from_str(self.order_type))
        if not isinstance(self.purpose, OrderPurpose):
            object.__setattr__(self, "purpose", OrderPurpose.from_str(self.purpose))


@dataclass(frozen=True, kw_only=True)
class OrderFilledEvent(DomainEvent):
    """Fired when an order fill execution is confirmed from exchange WebSocket/REST."""

    order_id: int
    trade_id: int
    symbol: str
    side: OrderSide
    purpose: OrderPurpose
    fill_price: Decimal
    fill_qty: Decimal
    fee: Decimal = Decimal("0")
    fee_asset: str = "USDT"
    exchange_order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    realized_pnl: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.FILLED

    def __post_init__(self) -> None:
        if not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide.from_str(self.side))
        if not isinstance(self.purpose, OrderPurpose):
            object.__setattr__(self, "purpose", OrderPurpose.from_str(self.purpose))
        if not isinstance(self.status, OrderStatus):
            object.__setattr__(self, "status", OrderStatus.from_str(self.status))


@dataclass(frozen=True, kw_only=True)
class OrderPartiallyFilledEvent(DomainEvent):
    """Fired when an order is partially executed on exchange."""

    order_id: int
    trade_id: int
    symbol: str
    side: OrderSide
    purpose: OrderPurpose
    fill_price: Decimal
    fill_qty: Decimal
    remaining_qty: Decimal
    cumulative_filled_qty: Decimal
    fee: Decimal = Decimal("0")
    fee_asset: str = "USDT"
    exchange_order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PARTIALLY_FILLED

    def __post_init__(self) -> None:
        if not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide.from_str(self.side))
        if not isinstance(self.purpose, OrderPurpose):
            object.__setattr__(self, "purpose", OrderPurpose.from_str(self.purpose))
        if not isinstance(self.status, OrderStatus):
            object.__setattr__(self, "status", OrderStatus.from_str(self.status))


@dataclass(frozen=True, kw_only=True)
class OrderCancelledEvent(DomainEvent):
    """Fired when an open order is cancelled on exchange."""

    order_id: int
    trade_id: int
    symbol: str
    purpose: OrderPurpose
    client_order_id: str
    exchange_order_id: Optional[str] = None
    reason: str = "CANCELLED_BY_SYSTEM"
    status: OrderStatus = OrderStatus.CANCELED

    def __post_init__(self) -> None:
        if not isinstance(self.purpose, OrderPurpose):
            object.__setattr__(self, "purpose", OrderPurpose.from_str(self.purpose))
        if not isinstance(self.status, OrderStatus):
            object.__setattr__(self, "status", OrderStatus.from_str(self.status))
