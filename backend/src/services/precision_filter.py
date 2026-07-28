"""Price and quantity precision helpers conforming to Binance exchange filters."""

import math
from dataclasses import dataclass


@dataclass
class SymbolInfo:
    """Exchange-level precision and lot-size filters for a trading symbol.

    Attributes:
        symbol: Trading pair name (e.g. ``BTCUSDT``).
        price_precision: Number of decimal places for prices.
        qty_precision: Number of decimal places for quantity.
        tick_size: Minimum price increment (e.g. ``0.10``).
        step_size: Minimum quantity increment (e.g. ``0.001``).
        min_qty: Minimum order quantity.
        min_notional: Minimum notional value in USDT (e.g. ``5.0``).
        max_qty: Maximum order quantity per request.
    """
    symbol: str
    price_precision: int
    qty_precision: int
    tick_size: float
    step_size: float
    min_qty: float
    min_notional: float
    max_qty: float = 99999999.0


class PrecisionFilterService:
    """Utility for rounding prices and quantities to Binance exchange rules."""

    @staticmethod
    def format_price(price: float, symbol_info: SymbolInfo) -> float:
        """Round ``price`` to the symbol's tick-size precision.

        Uses standard rounding (``round()``, banker's rounding).  Falls back
        to ``price_precision`` when ``tick_size`` is zero.
        """
        if symbol_info.tick_size > 0:
            precision = int(round(-math.log10(symbol_info.tick_size)))
            return round(price, precision)
        return round(price, symbol_info.price_precision)

    @staticmethod
    def format_qty(qty: float, symbol_info: SymbolInfo) -> float:
        """Floor ``qty`` to the symbol's step-size precision.

        The quantity is always rounded **down** to comply with Binance's
        LOT_SIZE filter (which rejects orders with quantities that are not
        a multiple of ``step_size``).
        """
        step = symbol_info.step_size
        if step > 0:
            precision = int(round(-math.log10(step)))
            factor = 10 ** precision
            return math.floor(qty * factor) / factor
        return round(qty, symbol_info.qty_precision)

    @staticmethod
    def validate_min_notional(qty: float, price: float, symbol_info: SymbolInfo) -> tuple[bool, str]:
        """Check whether the notional value (qty × price) satisfies Binance filters.

        Returns:
            A 2-tuple ``(is_valid, error_message)``.  ``error_message`` is
            empty when the order is compliant.
        """
        if qty < symbol_info.min_qty:
            return False, f"Qty ({qty}) below MIN_QTY ({symbol_info.min_qty})"
        notional_value = qty * price
        if notional_value < symbol_info.min_notional:
            return False, f"Notional (${notional_value:.2f}) below MIN_NOTIONAL (${symbol_info.min_notional})"
        return True, ""