"""Domain DTO entities for risk management and position sizing."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, List, Union, Any, Sequence

from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.price import Price
from src.domain.value_objects.quantity import Quantity
from src.domain.value_objects.leverage import Leverage


@dataclass(frozen=True)
class PositionSizingInput:
    """Standard input DTO parameter object for position sizing calculation."""

    wallet_balance: Union[Decimal, float]
    entry_price: Union[Decimal, Price, float]
    sl_price: Union[Decimal, Price, float]
    side: Optional[Union[OrderSide, str]] = None
    risk_percent: Decimal = Decimal("2.0")
    requested_leverage: Optional[Union[int, Leverage]] = None
    max_allowed_leverage: Union[int, Leverage] = 125

    # Instrument Market & Precision Specifications
    step_size: Union[Decimal, Quantity, float] = Decimal("0.001")
    tick_size: Union[Decimal, Price, float] = Decimal("0.1")
    qty_precision: int = 3
    price_precision: int = 2
    min_notional: Decimal = Decimal("5.0")

    # Optional Caps, Targets & Strict Mode
    max_risk_amount: Optional[Decimal] = None
    tp_targets: Sequence[Union[Decimal, Price, float]] = field(default_factory=list)

    tp_ratios: Optional[List[Decimal]] = None
    maint_margin_ratio: Decimal = Decimal("0.015")
    brackets: Optional[List[Any]] = None
    strict: bool = False  # If True, raises Domain Exceptions instead of returning is_valid=False with warnings


# Convenience alias
PositionSizingRequest = PositionSizingInput


@dataclass
class TPAllocationDTO:
    """Take profit order lot allocation."""

    tp_level: int
    price: Decimal
    quantity: Decimal
    percentage: Decimal
    is_close_all: bool = False

    @property
    def tp_number(self) -> int:
        return self.tp_level

    @property
    def target_price(self) -> Decimal:
        return self.price

    @property
    def allocated_qty(self) -> Decimal:
        return self.quantity



@dataclass
class RiskCalculationResultDTO:
    """Calculated position sizing, risk budget, and trade allocation."""

    risk_amount: Decimal
    stop_distance: Decimal
    position_size: Decimal
    required_margin: Decimal
    risk_percent: Decimal
    entry_price: Decimal
    sl_price: Decimal
    leverage: int
    requested_leverage: Optional[int] = None
    max_safe_leverage: Optional[int] = None
    is_leverage_downscaled: bool = False
    leverage_adjustment_reason: Optional[str] = None
    risk_reward_ratios: List[Decimal] = field(default_factory=list)
    tp_allocations: List[TPAllocationDTO] = field(default_factory=list)
    is_valid: bool = True
    warning: Optional[str] = None

    @property
    def stop_loss_price(self) -> Decimal:
        """Alias for sl_price."""
        return self.sl_price

    @property
    def margin_required(self) -> Decimal:
        """Alias for required_margin."""
        return self.required_margin

    @property
    def notional_value(self) -> Decimal:
        """Notional contract value."""
        return self.position_size * self.entry_price

    @property
    def estimated_liquidation_price(self) -> Optional[Decimal]:
        """Estimated liquidation price."""
        if self.entry_price <= Decimal("0") or self.leverage <= 0:
            return None
        return self.entry_price * (Decimal("1") - (Decimal("1") / Decimal(str(self.leverage))))
