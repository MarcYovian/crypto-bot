"""Order Entity/Aggregate encapsulated within Trade Aggregate."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, Union

from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.trade_status import OrderPurpose, OrderStatus, OrderType


@dataclass
class OrderAggregate:
    """Represents a single order belonging to a Trade Aggregate."""

    symbol: str
    side: OrderSide
    order_type: OrderType
    purpose: OrderPurpose
    quantity: Decimal
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    exchange_order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    trade_id: Optional[int] = None
    filled_qty: Decimal = field(default_factory=lambda: Decimal("0"))
    status: OrderStatus = OrderStatus.NEW
    created_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    id: Optional[int] = None

    def __post_init__(self) -> None:
        if isinstance(self.side, str):
            self.side = OrderSide.from_str(self.side)
        if isinstance(self.order_type, str):
            self.order_type = OrderType.from_str(self.order_type)
        if isinstance(self.purpose, str):
            self.purpose = OrderPurpose.from_str(self.purpose)
        if isinstance(self.status, str):
            self.status = OrderStatus.from_str(self.status)
        if not isinstance(self.quantity, Decimal):
            self.quantity = Decimal(str(self.quantity))
        if not isinstance(self.filled_qty, Decimal):
            self.filled_qty = Decimal(str(self.filled_qty))
        if self.created_at is None:
            self.created_at = datetime.now()

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED

    @property
    def is_active(self) -> bool:
        return self.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)

    def mark_filled(
        self,
        fill_price: Optional[Decimal] = None,
        fill_qty: Optional[Decimal] = None,
        filled_at: Optional[datetime] = None,
    ) -> None:
        """Transition order status to FILLED."""
        self.status = OrderStatus.FILLED
        if fill_qty is not None:
            self.filled_qty = Decimal(str(fill_qty))
        else:
            self.filled_qty = self.quantity
        if fill_price is not None:
            self.price = Decimal(str(fill_price))
        self.filled_at = filled_at or datetime.now()

    def mark_partially_filled(self, fill_qty: Decimal) -> None:
        """Record partial fill on order."""
        self.filled_qty += Decimal(str(fill_qty))
        self.status = OrderStatus.PARTIALLY_FILLED

    def mark_cancelled(self) -> None:
        """Transition order status to CANCELLED."""
        self.status = OrderStatus.CANCELLED
