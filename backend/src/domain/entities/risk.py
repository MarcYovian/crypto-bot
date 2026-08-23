"""Domain DTO entities for risk management and position sizing."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, List


@dataclass
class TPAllocationDTO:
    """Take profit order lot allocation."""
    tp_level: int
    price: Decimal
    quantity: Decimal
    percentage: Decimal
    is_close_all: bool = False


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
