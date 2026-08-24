"""Domain exceptions for bot runtime operations, circuit breaker, and settings."""

from src.domain.exceptions.base import DomainError


class BotOperationError(DomainError):
    """Base exception for failure during bot runtime operations."""
    pass


class PanicConfirmationRequiredError(BotOperationError):
    """Raised when emergency panic close is attempted without explicit confirmation."""
    pass


class InvalidSettingsValueError(BotOperationError):
    """Raised when setting parameters violate logical boundary limits."""
    pass


class InvalidDateRangeError(DomainError):
    """Raised when report date range start_date is after end_date."""
    pass


class InvalidLogLevelError(DomainError):
    """Raised when an unrecognized logging severity level is requested."""
    pass

