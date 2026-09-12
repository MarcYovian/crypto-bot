"""Pure domain service for financial decimal rounding and tick/step size quantization."""

from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import Optional, Union

from src.domain.value_objects.price import Price
from src.domain.value_objects.quantity import Quantity


class PrecisionFilterDomainService:
    """Pure domain service for rounding prices and quantities according to exchange precision rules."""

    @staticmethod
    def round_price(
        price: Union[Decimal, Price, float, int],
        tick_size: Union[Decimal, Price, float, int] = Decimal("0.1"),
        price_precision: int = 2,
    ) -> Decimal:
        """Round price to the nearest tick_size and decimal precision."""
        p = price.value if isinstance(price, Price) else Decimal(str(price))
        t = tick_size.value if isinstance(tick_size, Price) else Decimal(str(tick_size))
        if t <= Decimal("0"):
            t = Decimal("0.01")

        steps = (p / t).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        rounded = steps * t
        exp = Decimal(10) ** -price_precision if price_precision > 0 else Decimal("1")
        return rounded.quantize(exp, rounding=ROUND_HALF_UP)

    @staticmethod
    def round_quantity(
        qty: Union[Decimal, Quantity, float, int],
        step_size: Union[Decimal, Quantity, float, int] = Decimal("0.001"),
        qty_precision: int = 3,
        round_down: bool = True,
    ) -> Decimal:
        """Round order lot quantity, defaulting to floor rounding to prevent insufficient margin."""
        q = qty.value if isinstance(qty, Quantity) else Decimal(str(qty))
        s = step_size.value if isinstance(step_size, Quantity) else Decimal(str(step_size))
        if s <= Decimal("0"):
            s = Decimal("0.001")

        rounding_mode = ROUND_FLOOR if round_down else ROUND_HALF_UP
        steps = (q / s).quantize(Decimal("1"), rounding=rounding_mode)
        rounded = steps * s
        exp = Decimal(10) ** -qty_precision if qty_precision > 0 else Decimal("1")
        return rounded.quantize(exp, rounding=rounding_mode)

    @staticmethod
    def validate_min_notional(
        price: Union[Decimal, Price, float],
        qty: Union[Decimal, Quantity, float],
        min_notional: Union[Decimal, float] = Decimal("5.0"),
    ) -> bool:
        """Check if total order notional (price * qty) satisfies exchange minimum."""
        p = price.value if isinstance(price, Price) else Decimal(str(price))
        q = qty.value if isinstance(qty, Quantity) else Decimal(str(qty))
        mn = Decimal(str(min_notional))
        return (p * q) >= mn

    @staticmethod
    def clamp_leverage(
        leverage: Optional[int] = None,
        max_leverage: int = 125,
        min_leverage: int = 1,
        requested_leverage: Optional[int] = None,
    ) -> int:
        """Clamp requested leverage between allowed boundaries."""
        target = requested_leverage if requested_leverage is not None else (leverage or 1)
        return max(min_leverage, min(int(target), int(max_leverage)))


