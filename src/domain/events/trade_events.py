"""Domain events related to trade lifecycle transitions and state machine events."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, List, Union
from src.domain.events.base import DomainEvent
from src.domain.value_objects.side import OrderSide, MarginMode
from src.domain.value_objects.trade_status import TradeStatus, OrderPurpose


@dataclass(frozen=True, kw_only=True)
class TradeWaitingEntryEvent(DomainEvent):
    """Fired when a trade limit order is submitted and awaiting exchange fill."""

    trade_id: int
    account_id: int
    symbol: str
    side: OrderSide
    target_entry_price: Decimal
    position_size: Decimal
    leverage: int
    sl_price: Decimal
    tp1_price: Optional[Decimal] = None
    tp2_price: Optional[Decimal] = None
    tp3_price: Optional[Decimal] = None
    margin_mode: MarginMode = MarginMode.ISOLATED
    strategy_id: Optional[int] = None
    signal_id: Optional[int] = None

    def __post_init__(self) -> None:
        if not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide.from_str(self.side))
        if not isinstance(self.margin_mode, MarginMode):
            object.__setattr__(self, "margin_mode", MarginMode.from_str(self.margin_mode))


@dataclass(frozen=True, kw_only=True)
class TradeOpenedEvent(DomainEvent):
    """Fired when a trade entry order is filled and position becomes OPEN."""

    trade_id: int
    account_id: int
    symbol: str
    side: OrderSide
    entry_price: Decimal
    position_size: Decimal
    leverage: int
    sl_price: Decimal
    tp1_price: Optional[Decimal] = None
    tp2_price: Optional[Decimal] = None
    tp3_price: Optional[Decimal] = None
    margin_mode: MarginMode = MarginMode.ISOLATED
    strategy_id: Optional[int] = None
    signal_id: Optional[int] = None

    def __post_init__(self) -> None:
        if not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide.from_str(self.side))
        if not isinstance(self.margin_mode, MarginMode):
            object.__setattr__(self, "margin_mode", MarginMode.from_str(self.margin_mode))


@dataclass(frozen=True, kw_only=True)
class TradePartiallyClosedEvent(DomainEvent):
    """Fired when a TP target is hit and position is partially scaled out (PARTIAL status)."""

    trade_id: int
    account_id: int
    symbol: str
    target_hit: OrderPurpose  # OrderPurpose.TP1, OrderPurpose.TP2, OrderPurpose.TP3
    fill_price: Decimal
    closed_qty: Decimal
    remaining_qty: Decimal
    realized_pnl: Decimal
    new_sl_price: Optional[Decimal] = None
    side: Optional[Union[OrderSide, str]] = None

    def __post_init__(self) -> None:
        if not isinstance(self.target_hit, OrderPurpose):
            object.__setattr__(self, "target_hit", OrderPurpose.from_str(self.target_hit))
        if self.side is not None and not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide.from_str(self.side))


@dataclass(frozen=True, kw_only=True)
class StopLossMovedEvent(DomainEvent):
    """Fired when stop-loss is dynamically adjusted (e.g. moved to BEP or TP1)."""

    trade_id: int
    account_id: int
    symbol: str
    old_sl_price: Decimal
    new_sl_price: Decimal
    reason: str  # "BEP_AFTER_TP1", "TRAILING_AFTER_TP2", "MANUAL_ADJUST"
    side: Optional[Union[OrderSide, str]] = None

    def __post_init__(self) -> None:
        if self.side is not None and not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide.from_str(self.side))


@dataclass(frozen=True, kw_only=True)
class TradeClosedEvent(DomainEvent):
    """Fired when a trade position is completely closed."""

    trade_id: int
    account_id: int
    symbol: str
    exit_price: Decimal
    total_realized_pnl: Decimal
    close_reason: str  # "STOP_LOSS", "FINAL_TP", "MANUAL_CLOSE", "PANIC_CLOSE", "LIQUIDATION_FAILSAFE"
    closed_qty: Optional[Decimal] = None
    side: Optional[OrderSide] = None
    status: TradeStatus = TradeStatus.CLOSED

    def __post_init__(self) -> None:
        if self.side is not None and not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide.from_str(self.side))
        if not isinstance(self.status, TradeStatus):
            object.__setattr__(self, "status", TradeStatus.from_str(self.status))


@dataclass(frozen=True, kw_only=True)
class TradeCancelledEvent(DomainEvent):
    """Fired when a pending WAITING_ENTRY trade is cancelled before entry execution."""

    trade_id: int
    account_id: int
    symbol: str
    reason: str = "CANCELLED_BY_OPERATOR"
    status: TradeStatus = TradeStatus.CANCELLED

    def __post_init__(self) -> None:
        if not isinstance(self.status, TradeStatus):
            object.__setattr__(self, "status", TradeStatus.from_str(self.status))
