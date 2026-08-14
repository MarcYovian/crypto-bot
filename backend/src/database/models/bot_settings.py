"""BotSetting ORM model."""

from datetime import datetime
from typing import Optional
from sqlalchemy import Text, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from src.database.connection import Base


class BotSetting(Base):
    """Key-value store for persistent bot configuration.

    Attributes:
        key: Unique setting name (Primary Key).
        category: Setting category / group.
        type: Setting data type (e.g. STRING, INT, FLOAT, BOOL, JSON).
        value: Setting value.
        description: Optional human-readable explanation.
        updated_at: Timestamp of last update.
    """

    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    category: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    __table_args__ = (
        Index("idx_bot_settings_category", "category"),
    )
