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
    pass


class InsufficientBalanceError(InsufficientMarginError):
    """Alias for insufficient balance / funds."""
    pass


class OrderRejectError(ExchangeError):
    """Order rejected by exchange due to min notional, price filter, or lot step size."""
    pass


class RateLimitError(ExchangeError):
    """Exchange rate limit exceeded (HTTP 429 / IP ban warning)."""
    pass
