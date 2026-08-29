"""Value object representing leverage setting with tier validation."""

from dataclasses import dataclass
from typing import Union, Optional


@dataclass(frozen=True)
class Leverage:
    """Immutable Value Object for futures position leverage."""

    value: int

    def __init__(self, value: Union[int, str, float]) -> None:
        try:
            int_val = int(value)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid leverage value: {value}") from e

        if int_val < 1:
            raise ValueError(f"Leverage cannot be less than 1x: {int_val}")
        if int_val > 125:
            raise ValueError(f"Leverage cannot exceed exchange maximum 125x: {int_val}")

        object.__setattr__(self, "value", int_val)

    def validate_against_bracket(self, max_bracket_leverage: int) -> bool:
        """Check if leverage is allowed within the instrument's tier bracket."""
        return self.value <= max_bracket_leverage

    def cap_at(self, max_allowed: int) -> "Leverage":
        """Return new Leverage capped at max_allowed."""
        return Leverage(min(self.value, max_allowed))

    def as_int(self) -> int:
        return self.value

    def __int__(self) -> int:
        return self.value

    def __str__(self) -> str:
        return f"{self.value}x"

    def __repr__(self) -> str:
        return f"Leverage({self.value})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Leverage):
            return self.value == other.value
        if isinstance(other, int):
            return self.value == other
        return False
