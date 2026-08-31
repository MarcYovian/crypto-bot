"""Value objects and enums for trade, order, and position lifecycle states."""

from enum import Enum
from typing import Union


class TradeStatus(str, Enum):
    """Trade lifecycle status state machine."""

    WAITING_ENTRY = "WAITING_ENTRY"
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"

    @property
    def is_active(self) -> bool:
        """Return True if position is actively in the market or awaiting entry."""
        return self in (TradeStatus.WAITING_ENTRY, TradeStatus.OPEN, TradeStatus.PARTIAL)

    @property
    def is_open_position(self) -> bool:
        """Return True if position has been filled and is currently running."""
        return self in (TradeStatus.OPEN, TradeStatus.PARTIAL)

    @property
    def is_terminal(self) -> bool:
        """Return True if trade is completed or cancelled."""
        return self in (TradeStatus.CLOSED, TradeStatus.CANCELLED)

    @classmethod
    def from_str(cls, value: Union[str, "TradeStatus"]) -> "TradeStatus":
        if isinstance(value, TradeStatus):
            return value
        cleaned = str(value).strip().upper()
        for status in cls:
            if status.value == cleaned:
                return status
        raise ValueError(f"Invalid trade status: {value}")

    def __str__(self) -> str:
        return self.value


class OrderStatus(str, Enum):
    """Exchange order execution status."""

    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    CANCELLED = "CANCELED"  # Canonical alias pointing to CANCELED
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    PENDING = "PENDING"

    @property
    def is_open(self) -> bool:
        return self in (OrderStatus.PENDING, OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)

    @property
    def is_filled(self) -> bool:
        return self == OrderStatus.FILLED

    @property
    def is_terminal(self) -> bool:
        return self in (
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )

    @classmethod
    def from_str(cls, value: Union[str, "OrderStatus"]) -> "OrderStatus":
        if isinstance(value, OrderStatus):
            return value
        cleaned = str(value).strip().upper()
        # Normalization for exchange status variants
        if cleaned in ("OPEN", "NEW"):
            return cls.NEW
        if cleaned in ("FILLED", "CLOSED"):
            return cls.FILLED
        if cleaned in ("CANCELED", "CANCELLED"):
            return cls.CANCELED
        for status in cls:
            if status.value == cleaned:
                return status
        raise ValueError(f"Invalid order status: {value}")

    def __str__(self) -> str:
        return self.value


class OrderType(str, Enum):
    """Exchange order execution types."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    TRAILING_STOP_MARKET = "TRAILING_STOP_MARKET"

    @property
    def is_market(self) -> bool:
        return self in (OrderType.MARKET, OrderType.STOP_MARKET, OrderType.TAKE_PROFIT_MARKET)

    @property
    def is_limit(self) -> bool:
        return self == OrderType.LIMIT

    @property
    def is_stop(self) -> bool:
        return self in (OrderType.STOP_MARKET, OrderType.TRAILING_STOP_MARKET)

    @property
    def is_take_profit(self) -> bool:
        return self == OrderType.TAKE_PROFIT_MARKET

    @classmethod
    def from_str(cls, value: Union[str, "OrderType"]) -> "OrderType":
        if isinstance(value, OrderType):
            return value
        cleaned = str(value).strip().upper()
        # Standardize aliases
        if cleaned in ("STOP", "STOP_LOSS", "STOP_MARKET"):
            return cls.STOP_MARKET
        if cleaned in ("TP", "TAKE_PROFIT", "TAKE_PROFIT_MARKET"):
            return cls.TAKE_PROFIT_MARKET
        if cleaned in ("TRAILING", "TRAILING_STOP", "TRAILING_STOP_MARKET"):
            return cls.TRAILING_STOP_MARKET
        for o_type in cls:
            if o_type.value == cleaned:
                return o_type
        raise ValueError(f"Invalid order type: {value}")

    def __str__(self) -> str:
        return self.value


class OrderPurpose(str, Enum):
    """Functional role of an order within the trade lifecycle."""

    ENTRY = "ENTRY"
    TP1 = "TP1"
    TP2 = "TP2"
    TP3 = "TP3"
    SL = "SL"
    BEP_SL = "BEP_SL"
    TRAILING_SL = "TRAILING_SL"
    MANUAL_CLOSE = "MANUAL_CLOSE"
    PANIC_CLOSE = "PANIC_CLOSE"

    # Backward-compatible verbose aliases
    TAKE_PROFIT_1 = "TP1"
    TAKE_PROFIT_2 = "TP2"
    TAKE_PROFIT_3 = "TP3"
    STOP_LOSS = "SL"

    @property
    def is_tp(self) -> bool:
        return self in (OrderPurpose.TP1, OrderPurpose.TP2, OrderPurpose.TP3)

    @property
    def is_sl(self) -> bool:
        return self in (OrderPurpose.SL, OrderPurpose.BEP_SL, OrderPurpose.TRAILING_SL)

    @property
    def is_entry(self) -> bool:
        return self == OrderPurpose.ENTRY

    @property
    def is_bep(self) -> bool:
        return self == OrderPurpose.BEP_SL

    @property
    def is_trailing(self) -> bool:
        return self == OrderPurpose.TRAILING_SL

    @classmethod
    def from_str(cls, value: Union[str, "OrderPurpose"]) -> "OrderPurpose":
        if isinstance(value, OrderPurpose):
            return value
        cleaned = str(value).strip().upper()
        # Map verbose names and common aliases
        if cleaned in ("TP1", "TP_1", "TAKE_PROFIT_1"):
            return cls.TP1
        if cleaned in ("TP2", "TP_2", "TAKE_PROFIT_2"):
            return cls.TP2
        if cleaned in ("TP3", "TP_3", "TAKE_PROFIT_3"):
            return cls.TP3
        if cleaned in ("SL", "STOPLOSS", "STOP_LOSS"):
            return cls.SL
        if cleaned in ("BEP", "BEP_SL", "BREAK_EVEN"):
            return cls.BEP_SL
        if cleaned in ("TRAILING", "TRAILING_SL", "TRAILING_STOP"):
            return cls.TRAILING_SL
        if cleaned in ("MANUAL", "MANUAL_CLOSE", "CLOSE"):
            return cls.MANUAL_CLOSE
        if cleaned in ("PANIC", "PANIC_CLOSE"):
            return cls.PANIC_CLOSE
        for purpose in cls:
            if purpose.value == cleaned:
                return purpose
        raise ValueError(f"Invalid order purpose: {value}")

    def __str__(self) -> str:
        return self.value
