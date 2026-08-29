"""Watchlist ORM model."""

from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import Integer, Boolean, DateTime, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.persistence.connection import Base

if TYPE_CHECKING:
    from src.infrastructure.persistence.models.instruments import Instrument


class Watchlist(Base):
    """Instruments allowed for active trading.

    Attributes:
        id: Auto-increment primary key.
        instrument_id: FK to instruments table.
        enabled: Active enabled status flag.
        created_at: Record creation timestamp.
        updated_at: Record update timestamp.
    """

    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="TRUE")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    instrument: Mapped["Instrument"] = relationship("Instrument")

    __table_args__ = (
        UniqueConstraint("instrument_id", name="uk_watchlist_instrument_id"),
        Index("idx_watchlist_instrument_id", "instrument_id"),
        Index("idx_watchlist_enabled", "enabled"),
    )
