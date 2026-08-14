"""BotLog ORM model."""

from datetime import datetime
from typing import Optional
from sqlalchemy import Text, Integer, DateTime, CheckConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from src.database.connection import Base


class BotLog(Base):
    """Application log entry persisted to the database.

    Attributes:
        id: Auto-increment primary key.
        module: Application module / logger component name.
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        message: Log message text.
        context_json: Optional structured context as JSON.
        created_at: Log timestamp.
    """

    __tablename__ = "bot_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    module: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    __table_args__ = (
        CheckConstraint("level IN ('DEBUG','INFO','WARNING','ERROR','CRITICAL')", name="chk_bot_log_level"),
        Index("idx_bot_logs_level", "level"),
        Index("idx_bot_logs_module", "module"),
    )
