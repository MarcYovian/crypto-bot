"""Scheduler lifecycle manager for APScheduler background recurring jobs with database-driven recovery."""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional, Union
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.ports.gateways import IExchangeGateway, INotificationGateway
from src.domain.value_objects.misfire_policy import MisfirePolicy
from src.infrastructure.di.container import container
from src.infrastructure.scheduler.jobs import SchedulerJobs, WIB_TZ
from src.infrastructure.scheduler.task_registry import DEFAULT_SYSTEM_TASKS, calculate_next_fire_time

logger = logging.getLogger(__name__)


class SchedulerRunner:
    """Lifecycle manager for automated risk management, order maintenance, and system health jobs."""

    def __init__(
        self,
        jobs: Optional[SchedulerJobs] = None,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        session: Optional[AsyncSession] = None,
        exchange_gateway: Optional[IExchangeGateway] = None,
        notification_gateway: Optional[INotificationGateway] = None,
        **kwargs: Any,
    ) -> None:
        self.jobs = jobs or SchedulerJobs(
            session_factory=session_factory,
            session=session,
            exchange_gateway=exchange_gateway,
            notification_gateway=notification_gateway,
            **kwargs,
        )
        self.scheduler = AsyncIOScheduler(timezone=WIB_TZ)

    def __getattr__(self, name: str) -> Any:
        """Delegate job execution methods to the internal SchedulerJobs instance."""
        return getattr(self.jobs, name)

    async def run_startup_recovery(self) -> Dict[str, Any]:
        """Check and execute missed jobs following their MisfirePolicy upon bot startup."""
        logger.info("Executing Scheduler startup downtime recovery check...")
        async with self.jobs._get_session() as session:
            task_repo = container.get_scheduler_task_repo(session)

            # 1. Ensure default system tasks are seeded in DB
            for def_task in DEFAULT_SYSTEM_TASKS:
                existing = await task_repo.get(def_task["id"])
                if not existing:
                    next_fire = calculate_next_fire_time(def_task["cron_expr"])
                    await task_repo.upsert_task(
                        task_id=def_task["id"],
                        name=def_task["name"],
                        cron_expr=def_task["cron_expr"],
                        misfire_policy=def_task["misfire_policy"],
                        next_run_at=next_fire,
                    )

            now = datetime.now()
            overdue_tasks = await task_repo.get_overdue_tasks(reference_time=now)
            recovered: List[str] = []
            skipped: List[str] = []

            for task in overdue_tasks:
                if task.misfire_policy in (MisfirePolicy.RUN_LATEST_ONCE, MisfirePolicy.IMMEDIATE):
                    logger.warning(
                        "Downtime recovery: Task '%s' was missed (policy: %s). Executing catch-up run...",
                        task.id,
                        task.misfire_policy.value,
                    )
                    try:
                        await self.jobs.execute_job_by_id(task.id)
                        recovered.append(task.id)
                    except Exception as exc:
                        logger.error("Downtime recovery failed for '%s': %s", task.id, exc)
                elif task.misfire_policy == MisfirePolicy.SKIP_TO_NEXT:
                    logger.info(
                        "Downtime recovery: Task '%s' was missed (policy: SKIP_TO_NEXT). Advancing next run time...",
                        task.id,
                    )
                    next_fire = calculate_next_fire_time(task.cron_expr, reference_time=now)
                    await task_repo.update_next_run(task.id, next_fire)
                    skipped.append(task.id)

            await session.commit()
            logger.info(
                "Scheduler startup recovery complete: %d overdue tasks checked, %d recovered, %d skipped.",
                len(overdue_tasks),
                len(recovered),
                len(skipped),
            )
            return {
                "overdue_count": len(overdue_tasks),
                "recovered": recovered,
                "skipped": skipped,
            }

    async def update_task(
        self,
        task_id: str,
        name: Optional[str] = None,
        cron_expr: Optional[str] = None,
        is_active: Optional[bool] = None,
        misfire_policy: Optional[Union[MisfirePolicy, str]] = None,
        timezone_name: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> Any:
        """Unified function to update metadata, cron schedule, and active status for a scheduler task."""
        if session is not None:
            return await self._do_update_task(
                session, task_id, name, cron_expr, is_active, misfire_policy, timezone_name
            )
        async with self.jobs._get_session() as s:
            task = await self._do_update_task(
                s, task_id, name, cron_expr, is_active, misfire_policy, timezone_name
            )
            await s.commit()
            return task

    async def _do_update_task(
        self,
        session: AsyncSession,
        task_id: str,
        name: Optional[str] = None,
        cron_expr: Optional[str] = None,
        is_active: Optional[bool] = None,
        misfire_policy: Optional[Union[MisfirePolicy, str]] = None,
        timezone_name: Optional[str] = None,
    ) -> Any:
        task_repo = container.get_scheduler_task_repo(session)
        task = await task_repo.get(task_id)
        if not task:
            raise ValueError(f"Scheduler task with id '{task_id}' not found.")

        # 1. Update Name
        if name is not None:
            task.name = name

        # 2. Update Misfire Policy (ENUM)
        if misfire_policy is not None:
            task.misfire_policy = (
                misfire_policy
                if isinstance(misfire_policy, MisfirePolicy)
                else MisfirePolicy.from_str(misfire_policy)
            )

        # 3. Update Timezone
        if timezone_name is not None:
            task.timezone = timezone_name

        # 4. Update Cron Schedule (Live Reschedule)
        if cron_expr is not None:
            tz = timezone(task.timezone)
            # Validates format; raises ValueError if invalid
            new_trigger = CronTrigger.from_crontab(cron_expr, timezone=tz)

            task.cron_expr = cron_expr
            task.next_run_at = calculate_next_fire_time(cron_expr, tz_name=task.timezone)

            # Reschedule live job in memory if scheduler is running
            if self.scheduler.running and self.scheduler.get_job(task_id):
                self.scheduler.reschedule_job(task_id, trigger=new_trigger)

        # 5. Update Active Status (Live Pause / Resume)
        if is_active is not None:
            task.is_active = is_active
            if self.scheduler.running and self.scheduler.get_job(task_id):
                if is_active:
                    self.scheduler.resume_job(task_id)
                else:
                    self.scheduler.pause_job(task_id)

        await session.flush()
        await session.refresh(task)
        return task

    def start(self) -> None:
        """Register all 8 cron jobs and start APScheduler."""
        # 1. Daily Risk Snapshot at 00:00 WIB
        self.scheduler.add_job(
            self.jobs.run_daily_risk_snapshot_job,
            trigger=CronTrigger(hour=0, minute=0, timezone=WIB_TZ),
            id="daily_risk_snapshot",
            replace_existing=True,
        )

        # 2. Cleanup Orphan Orders every 30 minutes
        self.scheduler.add_job(
            self.jobs.run_cleanup_orphan_orders_job,
            trigger=CronTrigger(minute="0,30", timezone=WIB_TZ),
            id="cleanup_orphan_orders",
            replace_existing=True,
        )

        # 3. Failsafe Sync Check every 15 minutes
        self.scheduler.add_job(
            self.jobs.run_failsafe_sync_job,
            trigger=CronTrigger(minute="15,45", timezone=WIB_TZ),
            id="failsafe_sync_check",
            replace_existing=True,
        )

        # 4. Sync Instruments Metadata every 12 hours (06:00 & 18:00 WIB)
        self.scheduler.add_job(
            self.jobs.run_sync_instruments_metadata_job,
            trigger=CronTrigger(hour="6,18", minute=0, timezone=WIB_TZ),
            id="sync_instruments_metadata",
            replace_existing=True,
        )

        # 5. Purge Old Logs daily at 03:00 WIB
        self.scheduler.add_job(
            self.jobs.run_purge_old_logs_job,
            trigger=CronTrigger(hour=3, minute=0, timezone=WIB_TZ),
            id="purge_old_logs",
            replace_existing=True,
        )

        # 6. Daily Performance Report at 00:05 WIB
        self.scheduler.add_job(
            self.jobs.run_daily_performance_report_job,
            trigger=CronTrigger(hour=0, minute=5, timezone=WIB_TZ),
            id="daily_performance_report",
            replace_existing=True,
        )

        # 7. Heartbeat Health Check every hour
        self.scheduler.add_job(
            self.jobs.run_heartbeat_health_check_job,
            trigger=CronTrigger(minute=0, timezone=WIB_TZ),
            id="heartbeat_health_check",
            replace_existing=True,
        )

        # 8. Archive WebSocket Cache daily at 01:00 WIB
        self.scheduler.add_job(
            self.jobs.run_archive_ws_cache_job,
            trigger=CronTrigger(hour=1, minute=0, timezone=WIB_TZ),
            id="archive_ws_cache",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info("SchedulerRunner started with 8 recurring maintenance jobs.")

    def stop(self) -> None:
        """Shutdown APScheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("SchedulerRunner stopped.")

    @property
    def is_running(self) -> bool:
        """Check if background scheduler engine is currently running."""
        return self.scheduler.running


# Backward-compatible alias
SchedulerService = SchedulerRunner
