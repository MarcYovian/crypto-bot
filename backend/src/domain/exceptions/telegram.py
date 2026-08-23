"""Domain exceptions for Telegram Bot API and MTProto client interactions."""

from typing import Optional, Dict, Any
from src.domain.exceptions.base import DomainError


class TelegramError(DomainError):
    """Base exception for Telegram communication failures."""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details)


class TelegramAuthError(TelegramError):
    """Invalid bot token, unauthorized API access, or revoked session."""
    pass


class TelegramRateLimitError(TelegramError):
    """Telegram flood control limit exceeded (HTTP 429 / FloodWait)."""

    def __init__(
        self,
        message: str,
        retry_after: int = 30,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        details = details or {}
        details["retry_after"] = retry_after
        super().__init__(message, details)
        self.retry_after = retry_after


class TelegramNetworkError(TelegramError):
    """Network timeout, connection failure, or Telegram API unreachable."""
    pass


class TelegramSendError(TelegramError):
    """Message delivery failure (e.g. chat not found, user blocked bot)."""
    pass


class TelegramMessageParseError(TelegramError):
    """Formatting error in HTML or Markdown entity tags."""
    pass
