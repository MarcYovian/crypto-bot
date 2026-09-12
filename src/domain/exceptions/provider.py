"""Domain exceptions for Signal Providers and Trading Strategies."""

from src.domain.exceptions.base import DomainError


class ProviderNotFoundError(DomainError):
    """Raised when a signal provider is not found in the repository."""
    pass


class DuplicateProviderError(DomainError):
    """Raised when attempting to register a provider with an existing name or channel."""
    pass


class StrategyNotFoundError(DomainError):
    """Raised when a trading strategy is not found in the repository."""
    pass


class InvalidStrategyConfigError(DomainError):
    """Raised when a strategy configuration (e.g. TP percentages sum != 100) is invalid."""
    pass
