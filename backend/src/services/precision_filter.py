"""Deterministic decimal rounding and exchange precision filtering service."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import Optional, Any


@dataclass
class SymbolInfo:
    """Symbol market specifications and filter rules from exchange."""
    symbol: str
    price_precision: int = 2
    qty_precision: int = 3
    tick_size: float = 0.1
    min_qty: float = 0.001
    max_qty: float = 100000.0
    step_size: float = 0.001
    min_notional: float = 5.0
    max_leverage: int = 125


class PrecisionFilterService:
    """Utility service for rounding prices, quantities, and enforcing exchange limits."""

    @staticmethod
    def round_price(
        price: Decimal,
        tick_size: Decimal = Decimal("0.1"),
        price_precision: int = 2,
    ) -> Decimal:
        """Round price to the nearest tick_size and decimal precision.
        
        Args:
            price: Raw price value.
            tick_size: Minimum price increment (e.g. 0.1, 0.01).
            price_precision: Decimal places for display/API.
            
        Returns:
            Properly rounded Decimal price.
        """
        if tick_size <= Decimal("0"):
            tick_size = Decimal("0.01")
        steps = (price / tick_size).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        rounded = steps * tick_size
        exp = Decimal(10) ** -price_precision if price_precision > 0 else Decimal("1")
        return rounded.quantize(exp, rounding=ROUND_HALF_UP)

    @staticmethod
    def round_quantity(
        qty: Decimal,
        step_size: Decimal = Decimal("0.001"),
        qty_precision: int = 3,
        round_down: bool = True,
    ) -> Decimal:
        """Round order lot quantity, defaulting to floor rounding to prevent insufficient margin.
        
        Args:
            qty: Raw calculated quantity.
            step_size: Minimum lot step size (e.g. 0.001).
            qty_precision: Decimal places.
            round_down: If True (default), always truncate/floor down.
            
        Returns:
            Properly rounded Decimal quantity.
        """
        if step_size <= Decimal("0"):
            step_size = Decimal("0.001")
        rounding_mode = ROUND_FLOOR if round_down else ROUND_HALF_UP
        steps = (qty / step_size).quantize(Decimal("1"), rounding=rounding_mode)
        rounded = steps * step_size
        exp = Decimal(10) ** -qty_precision if qty_precision > 0 else Decimal("1")
        return rounded.quantize(exp, rounding=rounding_mode)

    @staticmethod
    def validate_min_notional(
        price: Decimal,
        qty: Decimal,
        min_notional: Decimal = Decimal("5.0"),
    ) -> bool:
        """Validate if the order value (price * qty) meets the exchange minimum notional.
        
        Args:
            price: Order price.
            qty: Order quantity.
            min_notional: Minimum order value threshold in quote asset (USDT).
            
        Returns:
            True if notional is greater than or equal to minimum.
        """
        return (price * qty) >= min_notional

    @staticmethod
    def format_qty(qty: Any, symbol_info: Any) -> float:
        """Format and round quantity to float using symbol_info specs."""
        step = getattr(symbol_info, "step_size", 0.001) or 0.001
        prec = getattr(symbol_info, "qty_precision", 3) or 3
        rounded = PrecisionFilterService.round_quantity(
            Decimal(str(qty)), step_size=Decimal(str(step)), qty_precision=prec, round_down=True
        )
        return float(rounded)

    @staticmethod
    def format_price(price: Any, symbol_info: Any) -> float:
        """Format and round price to float using symbol_info specs."""
        tick = getattr(symbol_info, "tick_size", 0.1) or 0.1
        prec = getattr(symbol_info, "price_precision", 2) or 2
        rounded = PrecisionFilterService.round_price(
            Decimal(str(price)), tick_size=Decimal(str(tick)), price_precision=prec
        )
        return float(rounded)

    @staticmethod
    def clamp_leverage(
        requested_leverage: int,
        max_leverage: int = 125,
        min_leverage: int = 1,
    ) -> int:
        """Ensure requested leverage is within allowable exchange bounds."""
        return max(min_leverage, min(requested_leverage, max_leverage))