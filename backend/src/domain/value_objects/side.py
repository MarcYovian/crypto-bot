"""Value objects and enums for order side, position side, and margin mode."""

from enum import Enum
from typing import Union


class OrderSide(str, Enum):
    """Trading order side: BUY or SELL."""

    BUY = "BUY"
    SELL = "SELL"

    @property
    def is_buy(self) -> bool:
        return self == OrderSide.BUY

    @property
    def is_sell(self) -> bool:
        return self == OrderSide.SELL

    @property
    def opposite(self) -> "OrderSide":
        """Return the opposite side for closing or reversing positions."""
        return OrderSide.SELL if self == OrderSide.BUY else OrderSide.BUY

    @classmethod
    def from_str(cls, value: Union[str, "OrderSide", None], default: Union["OrderSide", None] = None) -> "OrderSide":
        """Convert string to OrderSide enum safely with fallback."""
        if isinstance(value, OrderSide):
            return value
        if value is None:
            if default is not None:
                return default
            raise ValueError("Order side cannot be None")
        cleaned = str(value).strip().upper()
        if cleaned in ("BUY", "LONG"):
            return cls.BUY
        if cleaned in ("SELL", "SHORT"):
            return cls.SELL
        if default is not None:
            return default
        if cleaned in ("NONE", "UNKNOWN", ""):
            return cls.BUY  # Safe standard fallback
        raise ValueError(f"Invalid order side: {value}")

    def __str__(self) -> str:
        return self.value


class PositionSide(str, Enum):
    """Futures position orientation."""

    LONG = "LONG"
    SHORT = "SHORT"
    BOTH = "BOTH"

    @classmethod
    def from_str(cls, value: Union[str, "PositionSide"]) -> "PositionSide":
        if isinstance(value, PositionSide):
            return value
        cleaned = str(value).strip().upper()
        if cleaned in ("LONG", "BUY"):
            return cls.LONG
        if cleaned in ("SHORT", "SELL"):
            return cls.SHORT
        if cleaned == "BOTH":
            return cls.BOTH
        raise ValueError(f"Invalid position side: {value}")

    def __str__(self) -> str:
        return self.value


class MarginMode(str, Enum):
    """Futures account margin mode."""

    ISOLATED = "ISOLATED"
    CROSSED = "CROSSED"

    @classmethod
    def from_str(cls, value: Union[str, "MarginMode"]) -> "MarginMode":
        if isinstance(value, MarginMode):
            return value
        cleaned = str(value).strip().upper()
        if cleaned == "ISOLATED":
            return cls.ISOLATED
        if cleaned in ("CROSSED", "CROSS"):
            return cls.CROSSED
        raise ValueError(f"Invalid margin mode: {value}")

    def __str__(self) -> str:
        return self.value
