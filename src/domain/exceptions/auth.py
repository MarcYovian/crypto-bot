"""Domain exceptions for user authentication and authorization."""

from src.domain.exceptions.base import DomainError


class AuthError(DomainError):
    """Base exception for all authentication and authorization errors."""
    pass


class InvalidCredentialsError(AuthError):
    """Raised when authentication credentials are invalid or incorrect."""
    pass


class AccountDisabledError(AuthError):
    """Raised when account is inactive or disabled."""
    pass


class InvalidRefreshTokenError(AuthError):
    """Raised when refresh token is malformed, expired, or invalid."""
    pass


class UserNotFoundError(AuthError):
    """Raised when the specified user entity is not found."""
    pass
