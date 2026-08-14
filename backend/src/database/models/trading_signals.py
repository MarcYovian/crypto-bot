"""TradingSignal ORM model."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Text, Integer, Numeric, DateTime, ForeignKey, CheckConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.connection import Base

if TYPE_CHECKING:
    from src.database.models.signal_providers import SignalProvider
    from src.database.models.instruments import Instrument
    from src.database.models.trades import Trade


class TradingSignal(Base):
    """A trading signal parsed from an external signal provider.

    Tracks the full lifecycle from ``RECEIVED`` through ``EXECUTED`` or
    ``REJECTED``, with optional user confirmation for low-confidence signals.

    Attributes:
        id: Auto-increment primary key.
        provider_id: FK to signal_providers table.
        instrument_id: FK to instruments table.
        telegram_message_id: Original Telegram message ID (dedup).
        timeframe: Signal timeframe (e.g. 15m, 1h, 4h).
        side: ``BUY`` (long) or ``SELL`` (short).
        entry_min / entry_max: Entry price range.
        sl_price: Stop-loss price.
        tp1_price / tp2_price / tp3_price: Take-profit levels.
        confidence: AI / provider confidence score.
        raw_message: Unparsed raw message body.
        parsed_json: JSON string of parsed payload details.
        status: Lifecycle status.
        confirmation_status: User confirmation state.
        created_at: Record creation timestamp.
        updated_at: Record update timestamp.
    """

    __tablename__ = "trading_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("signal_providers.id", ondelete="RESTRICT"), nullable=False)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False)

    telegram_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    timeframe: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    side: Mapped[str] = mapped_column(Text, nullable=False)

    entry_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    entry_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    sl_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    tp1_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    tp2_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    tp3_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)

    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)
    raw_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parsed_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="RECEIVED")
    confirmation_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="NOT_REQUIRED")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    provider: Mapped["SignalProvider"] = relationship("SignalProvider")
    instrument: Mapped["Instrument"] = relationship("Instrument")
    trades: Mapped[List["Trade"]] = relationship(back_populates="signal")

    __table_args__ = (
        CheckConstraint("side IN ('BUY','SELL')", name="chk_signal_side"),
        CheckConstraint("status IN ('RECEIVED','EXECUTED','REJECTED','CANCELLED','EXPIRED')", name="chk_signal_status"),
        CheckConstraint("confirmation_status IN ('NOT_REQUIRED','PENDING','APPROVED','REJECTED')", name="chk_signal_confirm"),
        Index("idx_signal_provider_id", "provider_id"),
        Index("idx_signal_instrument_id", "instrument_id"),
        Index("idx_signal_status", "status"),
    )
