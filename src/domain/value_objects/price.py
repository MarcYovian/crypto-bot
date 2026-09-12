"""Value object representing financial price with strict Decimal precision."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_FLOOR
from typing import Union


@dataclass(frozen=True)
class Price:
    """Immutable Value Object for financial price."""

    value: Decimal

    def __init__(self, value: Union[Decimal, float, int, str]) -> None:
        if isinstance(value, Price):
            object.__setattr__(self, "value", value.value)
            return

        try:
            dec_val = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as e:
            raise ValueError(f"Invalid price value: {value}") from e

        if dec_val < Decimal("0"):
            raise ValueError(f"Price cannot be negative: {dec_val}")

        object.__setattr__(self, "value", dec_val)

    def round_to_tick(self, tick_size: Union[Decimal, "Price"]) -> "Price":
        """Quantize price to the exchange tick size."""
        tick = tick_size.value if isinstance(tick_size, Price) else Decimal(str(tick_size))
        if tick <= Decimal("0"):
            return self

        # Calculate number of decimal places from tick_size
        tick_str = f"{tick:f}"
        if "." in tick_str:
            decimals = len(tick_str.split(".")[1].rstrip("0"))
        else:
            decimals = 0

        # Standard quantize to tick
        rounded = (self.value / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick
        return Price(rounded.quantize(Decimal(f"1e-{decimals}") if decimals > 0 else Decimal("1")))

    @property
    def is_zero(self) -> bool:
        return self.value == Decimal("0")

    def as_decimal(self) -> Decimal:
        return self.value

    def __add__(self, other: Union["Price", Decimal, int, float]) -> "Price":
        other_val = other.value if isinstance(other, Price) else Decimal(str(other))
        return Price(self.value + other_val)

    def __sub__(self, other: Union["Price", Decimal, int, float]) -> "Price":
        other_val = other.value if isinstance(other, Price) else Decimal(str(other))
        return Price(self.value - other_val)

    def __mul__(self, other: Union[Decimal, int, float]) -> "Price":
        return Price(self.value * Decimal(str(other)))

    def __truediv__(self, other: Union[Decimal, int, float]) -> "Price":
        return Price(self.value / Decimal(str(other)))

    def __lt__(self, other: Union["Price", Decimal, int, float]) -> bool:
        other_val = other.value if isinstance(other, Price) else Decimal(str(other))
        return self.value < other_val

    def __le__(self, other: Union["Price", Decimal, int, float]) -> bool:
        other_val = other.value if isinstance(other, Price) else Decimal(str(other))
        return self.value <= other_val

    def __gt__(self, other: Union["Price", Decimal, int, float]) -> bool:
        other_val = other.value if isinstance(other, Price) else Decimal(str(other))
        return self.value > other_val

    def __ge__(self, other: Union["Price", Decimal, int, float]) -> bool:
        other_val = other.value if isinstance(other, Price) else Decimal(str(other))
        return self.value >= other_val

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Price):
            return self.value == other.value
        try:
            return self.value == Decimal(str(other))
        except (InvalidOperation, TypeError, ValueError):
            return False

    def __str__(self) -> str:
        return f"{self.value:f}"

    def __repr__(self) -> str:
        return f"Price({self.value})"
