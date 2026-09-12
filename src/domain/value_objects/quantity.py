"""Value object representing order and position quantity with strict precision."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP
from typing import Union


@dataclass(frozen=True)
class Quantity:
    """Immutable Value Object for position or order quantity."""

    value: Decimal

    def __init__(self, value: Union[Decimal, float, int, str]) -> None:
        if isinstance(value, Quantity):
            object.__setattr__(self, "value", value.value)
            return

        try:
            dec_val = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as e:
            raise ValueError(f"Invalid quantity value: {value}") from e

        if dec_val < Decimal("0"):
            raise ValueError(f"Quantity cannot be negative: {dec_val}")

        object.__setattr__(self, "value", dec_val)

    def round_to_step(self, step_size: Union[Decimal, "Quantity"], mode: str = "floor") -> "Quantity":
        """Quantize quantity to the exchange step size.
        
        Args:
            step_size: Minimum quantity increment (e.g. 0.001).
            mode: 'floor' (default, to prevent over-allocation) or 'half_up'.
        """
        step = step_size.value if isinstance(step_size, Quantity) else Decimal(str(step_size))
        if step <= Decimal("0"):
            return self

        step_str = f"{step:f}"
        if "." in step_str:
            decimals = len(step_str.split(".")[1].rstrip("0"))
        else:
            decimals = 0

        rounding = ROUND_FLOOR if mode == "floor" else ROUND_HALF_UP
        rounded = (self.value / step).quantize(Decimal("1"), rounding=rounding) * step
        return Quantity(rounded.quantize(Decimal(f"1e-{decimals}") if decimals > 0 else Decimal("1")))

    @property
    def is_zero(self) -> bool:
        return self.value == Decimal("0")

    def as_decimal(self) -> Decimal:
        return self.value

    def __add__(self, other: Union["Quantity", Decimal, int, float]) -> "Quantity":
        other_val = other.value if isinstance(other, Quantity) else Decimal(str(other))
        return Quantity(self.value + other_val)

    def __sub__(self, other: Union["Quantity", Decimal, int, float]) -> "Quantity":
        other_val = other.value if isinstance(other, Quantity) else Decimal(str(other))
        res = self.value - other_val
        if res < Decimal("0"):
            res = Decimal("0")
        return Quantity(res)

    def __mul__(self, other: Union[Decimal, int, float]) -> "Quantity":
        return Quantity(self.value * Decimal(str(other)))

    def __truediv__(self, other: Union[Decimal, int, float]) -> "Quantity":
        return Quantity(self.value / Decimal(str(other)))

    def __lt__(self, other: Union["Quantity", Decimal, int, float]) -> bool:
        other_val = other.value if isinstance(other, Quantity) else Decimal(str(other))
        return self.value < other_val

    def __le__(self, other: Union["Quantity", Decimal, int, float]) -> bool:
        other_val = other.value if isinstance(other, Quantity) else Decimal(str(other))
        return self.value <= other_val

    def __gt__(self, other: Union["Quantity", Decimal, int, float]) -> bool:
        other_val = other.value if isinstance(other, Quantity) else Decimal(str(other))
        return self.value > other_val

    def __ge__(self, other: Union["Quantity", Decimal, int, float]) -> bool:
        other_val = other.value if isinstance(other, Quantity) else Decimal(str(other))
        return self.value >= other_val

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Quantity):
            return self.value == other.value
        try:
            return self.value == Decimal(str(other))
        except (InvalidOperation, TypeError, ValueError):
            return False

    def __str__(self) -> str:
        return f"{self.value:f}"

    def __repr__(self) -> str:
        return f"Quantity({self.value})"
