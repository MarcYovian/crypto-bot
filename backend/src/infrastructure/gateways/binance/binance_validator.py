"""Pre-flight validation for Binance Futures operations before network execution."""

from decimal import Decimal
from typing import Optional, Union
from src.domain.value_objects.side import OrderSide, MarginMode
from src.domain.value_objects.trade_status import OrderType
from src.domain.value_objects.symbol import Symbol
from src.domain.value_objects.price import Price
from src.domain.value_objects.quantity import Quantity
from src.domain.value_objects.leverage import Leverage


class BinanceValidator:
    """Performs sanity and invariant checks on payloads before dispatching to CCXT."""

    @staticmethod
    def validate_symbol(symbol: str) -> str:
        """Validate and return normalized symbol."""
        if not symbol or not isinstance(symbol, str):
            raise ValueError(f"Invalid symbol: '{symbol}'. Must be a non-empty string.")
        return Symbol.normalize(symbol)

    @staticmethod
    def validate_leverage(leverage: Union[int, Leverage]) -> int:
        """Validate leverage bracket bounds."""
        lev_val = leverage.value if isinstance(leverage, Leverage) else leverage
        if lev_val < 1 or lev_val > 125:
            raise ValueError(f"Invalid leverage '{lev_val}'. Must be between 1x and 125x.")
        return lev_val

    @staticmethod
    def validate_margin_mode(margin_mode: Union[MarginMode, str]) -> str:
        """Validate margin mode string."""
        mode = margin_mode if isinstance(margin_mode, MarginMode) else MarginMode.from_str(margin_mode)
        return mode.value

    @classmethod
    def validate_order(
        cls,
        symbol: str,
        side: Union[OrderSide, str],
        order_type: Union[OrderType, str],
        qty: Union[Decimal, Quantity, float],
        price: Optional[Union[Decimal, Price, float]] = None,
    ) -> None:
        """Validate pre-flight order parameters."""
        cls.validate_symbol(symbol)

        q = qty.value if isinstance(qty, Quantity) else Decimal(str(qty))
        if q <= Decimal("0"):
            raise ValueError(f"Order quantity ({q}) must be strictly positive.")

        ot = order_type if isinstance(order_type, OrderType) else OrderType.from_str(order_type)
        if ot.is_limit:
            if price is None:
                raise ValueError("Price is strictly required for LIMIT orders.")
            p = price.value if isinstance(price, Price) else Decimal(str(price))
            if p <= Decimal("0"):
                raise ValueError(f"Order price ({p}) must be strictly positive.")
