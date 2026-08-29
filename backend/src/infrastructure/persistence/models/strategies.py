"""Strategy ORM model."""

from datetime import datetime
from typing import Optional
from sqlalchemy import Text, Integer, Boolean, DateTime, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.persistence.connection import Base


class Strategy(Base):
    """Trading strategy configuration and metadata.

    Attributes:
        id: Primary key (Auto increment).
        name: Strategy name identifier.
        version: Version string (e.g. 1.0.0).
        description: Optional strategy description / parameters overview.
        is_active: Active status flag.
        created_at: Record creation timestamp.
    """

    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="TRUE")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint("name", "version", name="uk_strategies_name_version"),
        Index("idx_strategies_is_active", "is_active"),
    )
