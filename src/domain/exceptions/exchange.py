"""Domain exceptions related to external exchange interactions (Binance/CCXT)."""

from typing import Optional, Dict, Any
from src.domain.exceptions.base import DomainError


class ExchangeError(DomainError):
    """Base exception for all exchange operation failures."""

    def __init__(
        self,
        message: str,
        exchange: str = "BINANCE",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details)
        self.exchange = exchange


class ExchangeNetworkError(ExchangeError):
    """Network connection timeout, DNS failure, or disconnection."""
    pass


class ExchangeAuthError(ExchangeError):
    """API key invalid, signature verification failure, or IP restriction."""
    pass


class InsufficientMarginError(ExchangeError):
    """Account has insufficient free margin to place order or maintain position."""

    def __init__(
        self,
        message: Optional[str] = None,
        exchange: str = "BINANCE",
        *,
        required_margin: Optional[Any] = None,
        available_margin: Optional[Any] = None,
        shortfall: Optional[Any] = None,
        position_size: Optional[Any] = None,
        notional: Optional[Any] = None,
        leverage: Optional[Any] = None,
        risk_amount: Optional[Any] = None,
        stop_distance: Optional[Any] = None,
        stop_percent: Optional[Any] = None,
        symbol: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        det = details or {}
        if required_margin is not None:
            det["required_margin"] = str(required_margin)
        if available_margin is not None:
            det["available_margin"] = str(available_margin)
        if shortfall is not None:
            det["shortfall"] = str(shortfall)
        if position_size is not None:
            det["position_size"] = str(position_size)
        if notional is not None:
            det["notional"] = str(notional)
        if leverage is not None:
            det["leverage"] = str(leverage)
        if risk_amount is not None:
            det["risk_amount"] = str(risk_amount)
        if stop_distance is not None:
            det["stop_distance"] = str(stop_distance)
        if stop_percent is not None:
            det["stop_percent"] = str(stop_percent)
        if symbol:
            det["symbol"] = symbol

        self.required_margin = required_margin
        self.available_margin = available_margin
        self.shortfall = det.get("shortfall")
        self.position_size = position_size
        self.notional = notional
        self.leverage = leverage
        self.risk_amount = risk_amount
        self.stop_distance = stop_distance
        self.stop_percent = stop_percent
        self.symbol = symbol

        if not message:
            req_str = f"{float(required_margin):.2f}" if required_margin is not None else "?"
            avail_str = f"{float(available_margin):.2f}" if available_margin is not None else "?"
            short_str = f" (Kekurangan: {float(self.shortfall):.2f} USDT)" if self.shortfall else ""
            message = f"Margin is insufficient: Required {req_str} USDT, Available {avail_str} USDT{short_str}."

        super().__init__(message, exchange=exchange, details=det)


class InsufficientBalanceError(InsufficientMarginError):
    """Alias for insufficient balance / funds."""
    pass


class OrderRejectError(ExchangeError):
    """Order rejected by exchange due to min notional, price filter, or lot step size."""
    pass


class RateLimitError(ExchangeError):
    """Exchange rate limit exceeded (HTTP 429 / IP ban warning)."""
    pass
