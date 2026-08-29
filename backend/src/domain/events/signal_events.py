"""Domain events related to signal lifecycle and validation."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, List, Union
from src.domain.events.base import DomainEvent
from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.trade_status import OrderType


@dataclass(frozen=True, kw_only=True)
class SignalReceivedEvent(DomainEvent):
    """Fired when a raw Telegram signal is parsed into a structured candidate."""

    signal_id: Optional[int] = None
    provider_id: Optional[int] = None
    symbol: str
    side: OrderSide
    order_type: OrderType = OrderType.LIMIT
    entry_min: Decimal = Decimal("0")
    entry_max: Decimal = Decimal("0")
    entry_targets: List[Decimal] = field(default_factory=list)
    sl_price: Decimal = Decimal("0")
    tp_targets: List[Decimal] = field(default_factory=list)
    leverage: Optional[int] = None
    timeframe: Optional[str] = None
    pattern: Optional[str] = None
    confidence_score: float = 1.0
    is_valid: bool = True
    raw_text: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide.from_str(self.side))
        if not isinstance(self.order_type, OrderType):
            object.__setattr__(self, "order_type", OrderType.from_str(self.order_type))


@dataclass(frozen=True, kw_only=True)
class SignalApprovedEvent(DomainEvent):
    """Fired when an operator approves a signal for automatic execution."""

    signal_id: int
    symbol: str
    approved_by: str
    side: Optional[Union[OrderSide, str]] = None
    entry_price: Optional[Decimal] = None
    sl_price: Optional[Decimal] = None
    calculated_lot_size: Optional[Decimal] = None
    leverage: Optional[int] = None
    trade_id: Optional[int] = None

    def __post_init__(self) -> None:
        if self.side and not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide.from_str(str(self.side)))


@dataclass(frozen=True, kw_only=True)
class SignalRejectedEvent(DomainEvent):
    """Fired when a signal is rejected (either validation failed or operator dismissed)."""

    signal_id: Optional[int] = None
    symbol: str
    reason: str
    side: Optional[Union[OrderSide, str]] = None
    rejected_by: str = "SYSTEM_VALIDATION"
    raw_text: Optional[str] = None

    def __post_init__(self) -> None:
        if self.side and not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide.from_str(str(self.side)))


@dataclass(frozen=True, kw_only=True)
class SignalExecutionFailedEvent(DomainEvent):
    """Fired when signal execution fails due to exchange rejection or risk limits."""

    signal_id: Optional[int] = None
    symbol: str
    error_message: str
    side: Optional[Union[OrderSide, str]] = None
    error_code: Optional[str] = None

    def __post_init__(self) -> None:
        if self.side and not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide.from_str(str(self.side)))
