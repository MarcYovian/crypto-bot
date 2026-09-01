"""Domain exceptions for trading signal processing and parsing."""

from typing import Optional, Dict, Any
from src.domain.exceptions.base import DomainError


class SignalParseError(DomainError):
    """Failed to extract essential trading parameters from raw signal text."""

    def __init__(
        self,
        message: str,
        raw_text: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        details = details or {}
        if raw_text:
            details["raw_text"] = raw_text
        super().__init__(message, details)


class InvalidSignalDataError(SignalParseError):
    """Signal parameters violate logical trading rules (e.g. SL higher than Entry for BUY)."""
    pass


class SignalNotFoundError(DomainError):
    """Requested signal ID does not exist."""
    pass
