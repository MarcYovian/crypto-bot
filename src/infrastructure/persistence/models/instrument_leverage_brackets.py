"""InstrumentLeverageBracket ORM model for storing exchange leverage and notional brackets."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from sqlalchemy import Integer, Numeric, DateTime, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.persistence.connection import Base

if TYPE_CHECKING:
    from src.infrastructure.persistence.models.instruments import Instrument


class InstrumentLeverageBracket(Base):
    """Tiered leverage and notional position limits per instrument from exchange.

    Attributes:
        id: Auto-increment primary key.
        instrument_id: FK to the parent instrument.
        bracket: Tier level number (1, 2, 3, etc.).
        initial_leverage: Maximum allowable leverage for this bracket.
        notional_cap: Maximum position notional value in USDT.
        notional_floor: Minimum position notional value in USDT.
        maint_margin_ratio: Maintenance margin requirement ratio (MMR).
        cum: Cumulative maintenance margin deduction factor.
        updated_at: Timestamp of the last sync.
    """

    __tablename__ = "instrument_leverage_brackets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )

    bracket: Mapped[int] = mapped_column(Integer, nullable=False)
    initial_leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    notional_cap: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    notional_floor: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    maint_margin_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    cum: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False, server_default="0")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    instrument: Mapped["Instrument"] = relationship("Instrument", back_populates="leverage_brackets")

    __table_args__ = (
        UniqueConstraint("instrument_id", "bracket", name="uk_instrument_brackets_bracket"),
        Index("idx_instrument_brackets_instrument_id", "instrument_id"),
    )
