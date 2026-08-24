"""Domain exceptions for risk calculations and position sizing constraints."""

from typing import Optional, Dict, Any
from src.domain.exceptions.base import DomainError


class RiskCalculationError(DomainError):
    """Base exception for failure during position sizing or risk calculation."""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details)


class ZeroStopDistanceError(RiskCalculationError):
    """Stop distance between entry price and stop loss price is zero."""
    pass


class MaxRiskExceededError(RiskCalculationError):
    """Calculated loss exceeds the maximum allowable daily or trade risk limit."""
    pass


class InsufficientMarginRiskError(RiskCalculationError):
    """Account free balance is insufficient to cover the required margin for the calculated size."""
    pass


class InvalidSignalGeometryError(RiskCalculationError):
    """Invalid price geometry for trade direction (e.g. SL higher than Entry for BUY)."""
    pass

