"""Repository implementation for SchedulerTask and SchedulerTaskRun entities."""

from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional, Union
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.ports.repositories import ISchedulerTaskRepository
from src.domain.value_objects.misfire_policy import MisfirePolicy
from src.infrastructure.persistence.models.scheduler_tasks import SchedulerTask, SchedulerTaskRun

logger = logging.getLogger(__name__)


class SchedulerTaskRepository(ISchedulerTaskRepository):
    """Data-access repository for managing scheduler tasks, next run times, and execution histories."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, task_id: str) -> Optional[SchedulerTask]:
        """Fetch a single scheduler task definition by its unique identifier."""
        stmt = select(SchedulerTask).where(SchedulerTask.id == task_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self, is_active: Optional[bool] = None) -> List[SchedulerTask]:
        """Fetch all registered scheduler tasks, optionally filtered by active status."""
        stmt = select(SchedulerTask)
        if is_active is not None:
            stmt = stmt.where(SchedulerTask.is_active == is_active)
        stmt = stmt.order_by(SchedulerTask.id.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_overdue_tasks(self, reference_time: datetime) -> List[SchedulerTask]:
        """Fetch active tasks where next_run_at <= reference_time."""
        stmt = (
            select(SchedulerTask)
            .where(
                SchedulerTask.is_active == True,  # noqa: E712
                SchedulerTask.next_run_at <= reference_time,
            )
            .order_by(SchedulerTask.next_run_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_task(
        self,
        task_id: str,
        name: str,
        cron_expr: str,
        misfire_policy: Union[str, MisfirePolicy],
        timezone: str = "Asia/Jakarta",
        is_active: bool = True,
        next_run_at: Optional[datetime] = None,
    ) -> SchedulerTask:
        """Create or update a scheduler task definition."""
        policy_enum = (
            misfire_policy
            if isinstance(misfire_policy, MisfirePolicy)
            else MisfirePolicy.from_str(misfire_policy)
        )

        task = await self.get(task_id)
        if task:
            task.name = name
            task.cron_expr = cron_expr
            task.timezone = timezone
            task.is_active = is_active
            task.misfire_policy = policy_enum
            if next_run_at is not None:
                task.next_run_at = next_run_at
        else:
            task = SchedulerTask(
                id=task_id,
                name=name,
                cron_expr=cron_expr,
                timezone=timezone,
                is_active=is_active,
                misfire_policy=policy_enum,
                next_run_at=next_run_at or datetime.now(),
                last_status="IDLE",
            )
            self.session.add(task)

        await self.session.flush()
        return task

    async def record_task_run(
        self,
        task_id: str,
        started_at: datetime,
        finished_at: datetime,
        status: str,
        next_run_at: Optional[datetime] = None,
        duration_ms: Optional[int] = None,
        result_summary: Optional[Union[str, Dict[str, Any]]] = None,
        error_message: Optional[str] = None,
    ) -> SchedulerTaskRun:
        """Record an execution log entry and advance the task's next_run_at timestamp."""
        summary_str: Optional[str] = None
        if result_summary is not None:
            if isinstance(result_summary, dict):
                summary_str = json.dumps(result_summary, default=str)
            else:
                summary_str = str(result_summary)

        run = SchedulerTaskRun(
            task_id=task_id,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            status=status.upper(),
            result_summary=summary_str,
            error_message=error_message,
        )
        self.session.add(run)

        # Update parent task state
        task = await self.get(task_id)
        if task:
            task.last_run_at = started_at
            task.last_status = status.upper()
            if next_run_at is not None:
                task.next_run_at = next_run_at

        await self.session.flush()
        return run

    async def update_next_run(self, task_id: str, next_run_at: datetime) -> None:
        """Update the next scheduled execution timestamp for a task."""
        task = await self.get(task_id)
        if task:
            task.next_run_at = next_run_at
            await self.session.flush()

    async def get_recent_runs(
        self, task_id: Optional[str] = None, limit: int = 50
    ) -> List[SchedulerTaskRun]:
        """Fetch historical execution run records."""
        stmt = select(SchedulerTaskRun)
        if task_id:
            stmt = stmt.where(SchedulerTaskRun.task_id == task_id)
        stmt = stmt.order_by(SchedulerTaskRun.started_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
