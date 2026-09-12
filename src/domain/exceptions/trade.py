"""Domain exceptions for trade lifecycle and position management."""

from typing import Optional, Dict, Any
from src.domain.exceptions.base import DomainError


class TradeExecutionError(DomainError):
    """Base exception for trade orchestration or execution failure."""

    def __init__(
        self,
        message: str,
        trade_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        details = details or {}
        if trade_id:
            details["trade_id"] = trade_id
        super().__init__(message, details)


class TradeNotFoundError(TradeExecutionError):
    """Trade record with the specified ID was not found."""
    pass


class InvalidTradeStateError(TradeExecutionError):
    """Attempted state transition violates trade state machine rules."""
    pass


class PairAlreadyActiveError(TradeExecutionError):
    """An active open position or pending order already exists for this symbol."""
    pass


class SymbolNotWhitelistedError(TradeExecutionError):
    """Symbol is not found in instruments table or is disabled in watchlist."""
    pass


class DailyRiskLimitReachedError(TradeExecutionError):
    """Circuit breaker is active or daily loss limit budget has been exhausted."""
    pass
