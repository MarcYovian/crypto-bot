"""Instrument ORM model."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from decimal import Decimal
from sqlalchemy import Text, Integer, Numeric, Boolean, DateTime, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.connection import Base

if TYPE_CHECKING:
    from src.database.models.exchange import Exchange


class Instrument(Base):
    """Trading symbol details and precision settings.

    Attributes:
        id: Primary key.
        exchange_id: FK to exchanges table.
        symbol: Trading pair code (e.g., BTCUSDT).
        base_asset: Base crypto asset (e.g., BTC).
        quote_asset: Quote crypto/fiat asset (e.g., USDT).
        tick_size: Minimum price movement step.
        step_size: Minimum quantity movement step.
        min_qty: Minimum order quantity allowed.
        min_notional: Minimum order value (price * qty) allowed.
        price_precision: Decimal places for price.
        qty_precision: Decimal places for quantity.
        is_active: Active trading status flag.
        updated_at: Record update timestamp.
    """

    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange_id: Mapped[int] = mapped_column(ForeignKey("exchanges.id", ondelete="RESTRICT"), nullable=False)
    
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    base_asset: Mapped[str] = mapped_column(Text, nullable=False)
    quote_asset: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Menggunakan Numeric/Decimal untuk presisi finansial crypto yang tinggi
    tick_size: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    step_size: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    min_qty: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    min_notional: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    
    price_precision: Mapped[int] = mapped_column(Integer, nullable=False)
    qty_precision: Mapped[int] = mapped_column(Integer, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="TRUE")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=func.current_timestamp(), 
        onupdate=func.current_timestamp()
    )

    # Relationships
    exchange: Mapped["Exchange"] = relationship("Exchange", back_populates="instruments")

    __table_args__ = (
        # Symbol harus unik per exchange
        UniqueConstraint("exchange_id", "symbol", name="uk_instruments_exchange_symbol"),
        Index("idx_instruments_symbol", "symbol"),
        Index("idx_instruments_is_active", "is_active"),
    )
