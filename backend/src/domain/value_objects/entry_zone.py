"""Value objects representing trading geometry, entry zones, and profit targets."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Union

from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.price import Price
from src.domain.exceptions.risk import (
    ZeroStopDistanceError,
    InvalidSignalGeometryError,
)


@dataclass(frozen=True)
class TakeProfitTarget:
    """Immutable Value Object for a take profit target level."""

    target_number: int
    price: Price
    allocation_percent: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.target_number < 1:
            raise ValueError("target_number must be >= 1")
        if not isinstance(self.price, Price):
            object.__setattr__(self, "price", Price(self.price))
        if not isinstance(self.allocation_percent, Decimal):
            object.__setattr__(self, "allocation_percent", Decimal(str(self.allocation_percent)))


@dataclass(frozen=True)
class EntryZone:
    """Immutable Value Object for multi-entry or single entry price boundaries."""

    entry_min: Price
    entry_max: Price
    targets: List[Price] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.entry_min, Price):
            object.__setattr__(self, "entry_min", Price(self.entry_min))
        if not isinstance(self.entry_max, Price):
            object.__setattr__(self, "entry_max", Price(self.entry_max))

    @property
    def avg_entry_price(self) -> Price:
        """Calculate the average expected entry price."""
        if self.targets:
            total = sum((p.value for p in self.targets), Decimal("0"))
            return Price(total / Decimal(str(len(self.targets))))
        if self.entry_min.value > 0 and self.entry_max.value > 0:
            return Price((self.entry_min.value + self.entry_max.value) / Decimal("2"))
        if self.entry_min.value > 0:
            return self.entry_min
        return self.entry_max


@dataclass(frozen=True)
class TradeGeometry:
    """Immutable Value Object encapsulating entry, stop-loss, and take-profit geometry validation."""

    side: OrderSide
    entry_price: Price
    sl_price: Price
    tp_targets: List[TakeProfitTarget] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide.from_str(self.side))
        if not isinstance(self.entry_price, Price):
            object.__setattr__(self, "entry_price", Price(self.entry_price))
        if not isinstance(self.sl_price, Price):
            object.__setattr__(self, "sl_price", Price(self.sl_price))

        # 1. Stop Distance validation
        stop_dist = abs(self.entry_price.value - self.sl_price.value)
        if stop_dist <= Decimal("0"):
            raise ZeroStopDistanceError(
                f"Invalid stop distance ({stop_dist}): Entry price ({self.entry_price}) and SL price ({self.sl_price}) cannot be equal."
            )

        # 2. Geometry relative to side
        if self.side.is_buy:
            if self.sl_price >= self.entry_price:
                raise InvalidSignalGeometryError(
                    f"Invalid geometry for BUY position: Stop Loss ({self.sl_price}) must be strictly below Entry Price ({self.entry_price})."
                )
            for tp in self.tp_targets:
                if tp.price <= self.entry_price:
                    raise InvalidSignalGeometryError(
                        f"Invalid geometry for BUY position: TP{tp.target_number} ({tp.price}) must be strictly above Entry Price ({self.entry_price})."
                    )
        elif self.side.is_sell:
            if self.sl_price <= self.entry_price:
                raise InvalidSignalGeometryError(
                    f"Invalid geometry for SELL position: Stop Loss ({self.sl_price}) must be strictly above Entry Price ({self.entry_price})."
                )
            for tp in self.tp_targets:
                if tp.price >= self.entry_price:
                    raise InvalidSignalGeometryError(
                        f"Invalid geometry for SELL position: TP{tp.target_number} ({tp.price}) must be strictly below Entry Price ({self.entry_price})."
                    )

    @property
    def stop_distance(self) -> Decimal:
        return abs(self.entry_price.value - self.sl_price.value)

    @property
    def risk_reward_ratios(self) -> List[Decimal]:
        """Calculate Risk-to-Reward ratio for all TP targets."""
        stop_dist = self.stop_distance
        if not self.tp_targets or stop_dist == Decimal("0"):
            return []
        return [
            abs(tp.price.value - self.entry_price.value) / stop_dist
            for tp in self.tp_targets
        ]

    @property
    def risk_reward_ratio_tp1(self) -> Optional[Decimal]:
        ratios = self.risk_reward_ratios
        return ratios[0] if ratios else None

