"""Exchange ORM model."""

from datetime import datetime
from typing import List, TYPE_CHECKING
from sqlalchemy import Text, Integer, DateTime, Index, func, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.connection import Base

if TYPE_CHECKING:
    from src.database.models.trading_accounts import TradingAccount
    from src.database.models.instruments import Instrument


class Exchange(Base):
    """Crypto exchange platform configuration.

    Attributes:
        id: Auto-increment primary key.
        code: Unique exchange code identifier (e.g. BINANCE, BYBIT).
        name: Human-readable exchange name.
        status: Active status of the exchange.
        created_at: Record creation timestamp.
        updated_at: Record update timestamp.
    """

    __tablename__ = "exchanges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="TRUE")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    trading_accounts: Mapped[List["TradingAccount"]] = relationship(
        "TradingAccount", back_populates="exchange", cascade="all, delete-orphan"
    )
    instruments: Mapped[List["Instrument"]] = relationship(
        "Instrument", back_populates="exchange", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_exchanges_status", "status"),
    )

