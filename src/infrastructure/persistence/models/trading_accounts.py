"""TradingAccount ORM model."""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Text, Integer, Boolean, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.persistence.connection import Base

if TYPE_CHECKING:
    from src.infrastructure.persistence.models.exchange import Exchange
    from src.infrastructure.persistence.models.trading_credentials import TradingCredential


class TradingAccount(Base):
    """Trading account associated with an exchange.

    Attributes:
        id: Primary key (Auto increment).
        exchange_id: FK to exchanges table.
        name: Account identifier / label.
        account_type: Type of account (e.g. SPOT, FUTURES, MARGIN).
        environment: Trading environment (e.g. MAINNET, TESTNET).
        is_active: Status active flag.
        created_at: Record creation timestamp.
        updated_at: Record update timestamp.
    """

    __tablename__ = "trading_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange_id: Mapped[int] = mapped_column(ForeignKey("exchanges.id", ondelete="RESTRICT"), nullable=False)
    
    name: Mapped[str] = mapped_column(Text, nullable=False)
    account_type: Mapped[str] = mapped_column(Text, nullable=False)
    environment: Mapped[str] = mapped_column(Text, nullable=False, server_default="MAINNET")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="TRUE")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=func.current_timestamp(), 
        onupdate=func.current_timestamp()
    )

    # Relationships
    exchange: Mapped["Exchange"] = relationship("Exchange", back_populates="trading_accounts")
    credentials: Mapped[List["TradingCredential"]] = relationship(
        "TradingCredential", back_populates="account", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_trading_accounts_exchange_id", "exchange_id"),
        Index("idx_trading_accounts_is_active", "is_active"),
    )
