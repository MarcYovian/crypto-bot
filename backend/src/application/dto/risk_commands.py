"""Data Transfer Objects and Commands for Risk Use Cases."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SimulateRiskCommand:
    """Command payload for simulating position sizing on dashboard."""

    symbol: str
    side: str
    entry_price: Decimal
    sl_price: Decimal
    tp_targets: List[Decimal]
    leverage: Optional[int] = None
    account_id: int = 1
    custom_balance: Optional[Decimal] = None
    risk_percent: Optional[Decimal] = None


@dataclass(frozen=True)
class CheckDailyRiskCommand:
    """Command payload to evaluate daily risk limit & circuit breaker status."""

    account_id: int = 1
    today_date: Optional[Any] = None
