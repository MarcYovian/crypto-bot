"""Domain DTO entities for parsed trading signals."""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, List


@dataclass
class SignalTargetDTO:
    """Take profit target specification."""
    target_number: int
    price: Decimal
    allocation_percent: Optional[Decimal] = None


@dataclass
class ParsedSignalDTO:
    """Structured data transfer object representing a parsed Telegram signal."""
    raw_text: str
    symbol: str
    side: str  # "BUY" or "SELL"
    order_type: str = "LIMIT"  # "MARKET" or "LIMIT"
    entry_min: Decimal = Decimal("0")
    entry_max: Decimal = Decimal("0")
    entry_targets: List[Decimal] = field(default_factory=list)
    sl_price: Decimal = Decimal("0")
    tp_targets: List[Decimal] = field(default_factory=list)
    leverage: Optional[int] = None
    confidence_score: float = 1.0
    is_valid: bool = True
    error_message: Optional[str] = None
    trace_id: str = field(default_factory=lambda: f"sig-{uuid.uuid4().hex[:8]}")

    @property
    def avg_entry_price(self) -> Decimal:
        """Calculate average expected entry price."""
        if self.entry_targets:
            return sum(self.entry_targets) / Decimal(str(len(self.entry_targets)))
        if self.entry_min > 0 and self.entry_max > 0:
            return (self.entry_min + self.entry_max) / Decimal("2")
        return self.entry_min or self.entry_max
