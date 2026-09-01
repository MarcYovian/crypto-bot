"""TradingCredential ORM model."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Text, Integer, Boolean, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.persistence.connection import Base

if TYPE_CHECKING:
    from src.infrastructure.persistence.models.trading_accounts import TradingAccount


class TradingCredential(Base):
    """Encrypted API credentials for an exchange trading account.

    Attributes:
        id: Primary key (Auto increment).
        account_id: FK to trading_accounts table.
        key_name: Label / identifier for this key pair.
        encrypted_api_key: Encrypted API key.
        encrypted_secret_key: Encrypted secret key.
        encrypted_passphrase: Encrypted passphrase (required by some exchanges like OKX/KuCoin).
        key_version: Key rotation version number.
        is_active: Active status flag.
        created_at: Record creation timestamp.
        updated_at: Record update timestamp.
    """

    __tablename__ = "trading_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=False)
    
    key_name: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_secret_key: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_passphrase: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="TRUE")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=func.current_timestamp(), 
        onupdate=func.current_timestamp()
    )

    # Relationships
    account: Mapped["TradingAccount"] = relationship("TradingAccount", back_populates="credentials")

    __table_args__ = (
        Index("idx_trading_credentials_account_id", "account_id"),
        Index("idx_trading_credentials_is_active", "is_active"),
    )
