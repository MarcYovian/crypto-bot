"""SignalProvider ORM model."""

from datetime import datetime
from sqlalchemy import Text, Integer, Boolean, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.persistence.connection import Base


class SignalProvider(Base):
    """Signal provider / webhook / indicator source.

    Attributes:
        id: Primary key (Auto increment).
        name: Provider name identifier (e.g., TradingView Webhook, Telegram Channel).
        type: Provider type / protocol (e.g., WEBHOOK, REST_API, INTERNAL).
        is_active: Active status flag.
        created_at: Record creation timestamp.
    """

    __tablename__ = "signal_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="TRUE")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    __table_args__ = (
        Index("idx_signal_providers_is_active", "is_active"),
        Index("idx_signal_providers_type", "type"),
    )
