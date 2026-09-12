"""Domain exceptions for risk calculations and position sizing constraints."""

from decimal import Decimal
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

    def __init__(
        self,
        message: Optional[str] = None,
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
        elif required_margin is not None and available_margin is not None:
            try:
                det["shortfall"] = str(max(Decimal("0"), Decimal(str(required_margin)) - Decimal(str(available_margin))))
            except Exception:
                pass
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
            message = f"Margin tidak mencukupi: Dibutuhkan {req_str} USDT, Tersedia {avail_str} USDT{short_str}."

        super().__init__(message, details=det)


class InvalidSignalGeometryError(RiskCalculationError):
    """Invalid price geometry for trade direction (e.g. SL higher than Entry for BUY)."""
    pass


class StopLossCannotExceedEntryError(InvalidSignalGeometryError):
    """Stop Loss adjustment violates risk reduction invariant."""
    pass


