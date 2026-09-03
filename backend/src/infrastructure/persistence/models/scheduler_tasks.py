"""ORM models for Database-Driven Scheduler tasks and execution logs."""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.value_objects.misfire_policy import MisfirePolicy
from src.infrastructure.persistence.connection import Base


class SchedulerTask(Base):
    """Database entity defining a recurring scheduler task, its cron schedule, and runtime state."""

    __tablename__ = "scheduler_tasks"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    cron_expr: Mapped[str] = mapped_column(String(50), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="Asia/Jakarta")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    misfire_policy: Mapped[MisfirePolicy] = mapped_column(
        SQLEnum(MisfirePolicy, name="misfire_policy_enum", native_enum=False),
        nullable=False,
        default=MisfirePolicy.RUN_LATEST_ONCE,
    )
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_status: Mapped[str] = mapped_column(String(20), nullable=False, default="IDLE")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    runs: Mapped[List["SchedulerTaskRun"]] = relationship(
        "SchedulerTaskRun", back_populates="task", cascade="all, delete-orphan", order_by="desc(SchedulerTaskRun.started_at)"
    )

    __table_args__ = (
        Index("idx_scheduler_next_run", "is_active", "next_run_at"),
    )


class SchedulerTaskRun(Base):
    """Execution audit log for an individual scheduler job invocation."""

    __tablename__ = "scheduler_task_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("scheduler_tasks.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # 'SUCCESS', 'FAILED'
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    task: Mapped["SchedulerTask"] = relationship("SchedulerTask", back_populates="runs")

    __table_args__ = (
        Index("idx_task_runs_history", "task_id", "started_at"),
    )
