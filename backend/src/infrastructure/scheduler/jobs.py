"""Automated background scheduler service for risk management, order maintenance, and system health.

Acts as a Thin Driving Adapter triggering Clean Architecture Application Use Cases
with full database-driven execution tracking, dynamic activation, and misfire recovery.
"""

from contextlib import asynccontextmanager
from datetime import date, datetime
import logging
from typing import Any, AsyncIterator, Callable, Dict, List, Optional
from pytz import timezone
from unittest.mock import Mock
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.persistence.connection import AsyncSessionLocal
from src.infrastructure.di.container import container
from src.domain.ports.gateways import IExchangeGateway, INotificationGateway
from src.application.dto.trade_commands import SyncPositionsCommand
from src.application.use_cases.risk.daily_risk_snapshot_use_case import DailyRiskSnapshotUseCase
from src.application.use_cases.trades.cleanup_orphan_orders_use_case import CleanupOrphanOrdersUseCase
from src.application.use_cases.trades.sync_positions_use_case import SyncPositionsUseCase
from src.application.use_cases.instruments.sync_instruments_use_case import SyncInstrumentsUseCase
from src.application.use_cases.logs.purge_old_logs_use_case import PurgeOldLogsUseCase
from src.application.use_cases.reports.send_daily_performance_report_use_case import SendDailyPerformanceReportUseCase
from src.application.use_cases.bot.check_system_heartbeat_use_case import CheckSystemHeartbeatUseCase
from src.infrastructure.scheduler.task_registry import calculate_next_fire_time
from src.utils.ws_cache_logger import archive_ws_cache


logger = logging.getLogger(__name__)
WIB_TZ = timezone("Asia/Jakarta")


class SchedulerJobs:
    """Thin Driving Adapter orchestrating background recurring maintenance jobs via Application Use Cases."""

    TASK_METHOD_MAP: Dict[str, str] = {
        "daily_risk_snapshot": "run_daily_risk_snapshot_job",
        "cleanup_orphan_orders": "run_cleanup_orphan_orders_job",
        "failsafe_sync_check": "run_failsafe_sync_job",
        "sync_instruments_metadata": "run_sync_instruments_metadata_job",
        "purge_old_logs": "run_purge_old_logs_job",
        "daily_performance_report": "run_daily_performance_report_job",
        "heartbeat_health_check": "run_heartbeat_health_check_job",
        "archive_ws_cache": "run_archive_ws_cache_job",
    }

    def __init__(
        self,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        session: Optional[AsyncSession] = None,
        exchange_gateway: Optional[IExchangeGateway] = None,
        notification_gateway: Optional[INotificationGateway] = None,
        **kwargs: Any,
    ) -> None:
        self.session_factory = session_factory or AsyncSessionLocal
        self.session = session
        self.exchange_gateway = exchange_gateway
        self.notification_gateway = notification_gateway

        # Retain any mock use case overrides injected during tests
        self._instrument_service = kwargs.get("instrument_service")
        self._position_manager = kwargs.get("position_manager")

        # Absorb any real database session from kwargs if provided (ignoring Mock instances)
        if self.session is None:
            for val in kwargs.values():
                if val and not isinstance(val, Mock):
                    s = getattr(val, "session", None)
                    if s is not None and not isinstance(s, Mock):
                        self.session = s
                        break

    @asynccontextmanager
    async def _get_session(self) -> AsyncIterator[AsyncSession]:
        """Provide a scoped database session per job execution."""
        if self.session is not None:
            yield self.session
        else:
            factory = self.session_factory or AsyncSessionLocal
            async with factory() as session:
                try:
                    yield session
                except Exception:
                    await session.rollback()
                    raise

    async def _run_task_with_db_tracking(
        self, session: AsyncSession, task_id: str, action_coro: Callable[[], Any]
    ) -> Any:
        """Wrap execution with database state checking, duration timing, audit logging, and next run calculation."""
        task = None
        task_repo = None
        if not isinstance(session, Mock):
            try:
                task_repo = container.get_scheduler_task_repo(session)
                task = await task_repo.get(task_id)
            except Exception as get_exc:
                logger.debug("Task '%s' state could not be read from DB: %s", task_id, get_exc)

        # Check if task is paused/inactive in database
        if task and not task.is_active:
            logger.info("Task '%s' is inactive in database. Skipping scheduled execution.", task_id)
            return None

        started_at = datetime.now()
        error_msg: Optional[str] = None
        status = "SUCCESS"
        result = None

        try:
            result = await action_coro()
            return result
        except Exception as exc:
            status = "FAILED"
            error_msg = str(exc)
            raise
        finally:
            finished_at = datetime.now()
            duration_ms = int((finished_at - started_at).total_seconds() * 1000)
            next_fire: Optional[datetime] = None
            if task and task.cron_expr:
                next_fire = calculate_next_fire_time(task.cron_expr, reference_time=finished_at)

            if task_repo and not isinstance(session, Mock):
                try:
                    await task_repo.record_task_run(
                        task_id=task_id,
                        started_at=started_at,
                        finished_at=finished_at,
                        status=status,
                        next_run_at=next_fire,
                        duration_ms=duration_ms,
                        result_summary=result if isinstance(result, (dict, list, int, str)) else None,
                        error_message=error_msg,
                    )
                except Exception as audit_exc:
                    logger.debug("Could not record task run for '%s': %s", task_id, audit_exc)

    async def execute_job_by_id(self, task_id: str) -> Any:
        """Execute a registered scheduler job by its task_id."""
        method_name = self.TASK_METHOD_MAP.get(task_id)
        if not method_name or not hasattr(self, method_name):
            raise ValueError(f"Unknown scheduler task ID: '{task_id}'")
        return await getattr(self, method_name)()

    # =========================================================================
    # JOB 1: Daily Risk Snapshot (00:00 WIB)
    # =========================================================================
    async def run_daily_risk_snapshot_job(
        self, account_id: int = 1, snapshot_date: Optional[date] = None
    ) -> Any:
        """Lock initial balance at midnight and compute daily risk budget via DailyRiskSnapshotUseCase."""
        async with self._get_session() as session:
            async def _action():
                use_case = DailyRiskSnapshotUseCase(
                    daily_risk_repo=container.get_daily_risk_repo(session),
                    risk_profile_repo=container.get_risk_profile_repo(session),
                    bot_setting_repo=container.get_bot_setting_repo(session),
                    exchange_gateway=self.exchange_gateway or container.exchange_gateway,
                    notification_gateway=self.notification_gateway or container.notification_gateway,
                )
                return await use_case.execute(account_id=account_id, snapshot_date=snapshot_date)

            res = await self._run_task_with_db_tracking(session, "daily_risk_snapshot", _action)
            await session.commit()
            return res

    # =========================================================================
    # JOB 2: Cleanup Orphan Orders (Every 30 Minutes)
    # =========================================================================
    async def run_cleanup_orphan_orders_job(
        self, account_id: int = 1, max_age_hours: int = 4
    ) -> int:
        """Cancel pending WAITING_ENTRY limit orders older than max_age_hours via CleanupOrphanOrdersUseCase."""
        async with self._get_session() as session:
            async def _action():
                use_case = CleanupOrphanOrdersUseCase(
                    trade_repo=container.get_trade_repo(session),
                    order_repo=container.get_order_repo(session),
                    instrument_repo=container.get_instrument_repo(session),
                    trade_event_repo=container.get_trade_event_repo(session),
                    exchange_gateway=self.exchange_gateway or container.exchange_gateway,
                )
                return await use_case.execute(account_id=account_id, max_age_hours=max_age_hours)

            res = await self._run_task_with_db_tracking(session, "cleanup_orphan_orders", _action)
            await session.commit()
            return res if res is not None else 0

    # =========================================================================
    # JOB 3: Failsafe Sync Check (Every 15 Minutes)
    # =========================================================================
    async def run_failsafe_sync_job(self, account_id: int = 1) -> Dict[str, Any]:
        """Reconcile database active trades with live exchange open positions via SyncPositionsUseCase."""
        async with self._get_session() as session:
            async def _action():
                client = self.exchange_gateway or container.exchange_gateway
                use_case = (
                    self._position_manager
                    if isinstance(self._position_manager, SyncPositionsUseCase)
                    else SyncPositionsUseCase(
                        trade_repo=container.get_trade_repo(session),
                        instrument_repo=container.get_instrument_repo(session),
                        exchange_gateway=client,
                        order_repo=container.get_order_repo(session),
                        execution_repo=container.get_execution_repo(session),
                        trade_summary_repo=container.get_trade_summary_repo(session),
                        event_publisher=container.event_publisher,
                    )
                )

                cmd = SyncPositionsCommand(account_id=account_id)
                result = await use_case.execute(cmd)

                synced = result.get("synced_trades", 0)
                desynced = result.get("desynced_trades", 0)
                result["total_checked"] = synced + desynced
                result["desynced_closed"] = desynced
                return result

            res = await self._run_task_with_db_tracking(session, "failsafe_sync_check", _action)
            await session.commit()
            return res if res is not None else {"status": "SKIPPED", "total_checked": 0, "desynced_closed": 0}

    # =========================================================================
    # JOB 4: Sync Instruments Metadata (Every 12 Hours)
    # =========================================================================
    async def run_sync_instruments_metadata_job(self, exchange_id: int = 1) -> int:
        """Fetch updated symbol filters from exchange and bulk-upsert into instruments table."""
        if self._instrument_service and hasattr(self._instrument_service, "sync_all_instruments"):
            return await self._instrument_service.sync_all_instruments(exchange_id=exchange_id)

        async with self._get_session() as session:
            async def _action():
                use_case = SyncInstrumentsUseCase(
                    instrument_repo=container.get_instrument_repo(session),
                    exchange_repo=container.get_exchange_repo(session),
                    exchange_gateway=self.exchange_gateway or container.exchange_gateway,
                )
                return await use_case.sync_all_instruments(exchange_id=exchange_id)

            res = await self._run_task_with_db_tracking(session, "sync_instruments_metadata", _action)
            await session.commit()
            return res if res is not None else 0

    # =========================================================================
    # JOB 5: Purge Old Logs (Daily at 03:00 WIB)
    # =========================================================================
    async def run_purge_old_logs_job(self, days: int = 30) -> int:
        """Purge system logs older than retention days via PurgeOldLogsUseCase."""
        async with self._get_session() as session:
            async def _action():
                use_case = PurgeOldLogsUseCase(log_repo=container.get_bot_log_repo(session))
                return await use_case.execute(days=days)

            res = await self._run_task_with_db_tracking(session, "purge_old_logs", _action)
            await session.commit()
            return res if res is not None else 0

    # =========================================================================
    # JOB 6: Daily Performance Report (00:05 WIB)
    # =========================================================================
    async def run_daily_performance_report_job(self, account_id: int = 1) -> Dict[str, Any]:
        """Aggregate yesterday's closed trades and send daily performance report to Telegram."""
        async with self._get_session() as session:
            async def _action():
                use_case = SendDailyPerformanceReportUseCase(
                    trade_summary_repo=container.get_trade_summary_repo(session),
                    notification_gateway=self.notification_gateway or container.notification_gateway,
                )
                return await use_case.execute(account_id=account_id)

            res = await self._run_task_with_db_tracking(session, "daily_performance_report", _action)
            await session.commit()
            return res if res is not None else {}

    # =========================================================================
    # JOB 7: Heartbeat Health Check (Every 1 Hour)
    # =========================================================================
    async def run_heartbeat_health_check_job(self) -> Dict[str, Any]:
        """Perform system-wide health check and record log audit via CheckSystemHeartbeatUseCase."""
        async with self._get_session() as session:
            async def _action():
                use_case = CheckSystemHeartbeatUseCase(
                    bot_setting_repo=container.get_bot_setting_repo(session),
                    bot_log_repo=container.get_bot_log_repo(session),
                    exchange_gateway=self.exchange_gateway or container.exchange_gateway,
                )
                return await use_case.execute()

            res = await self._run_task_with_db_tracking(session, "heartbeat_health_check", _action)
            await session.commit()
            return res if res is not None else {}

    # =========================================================================
    # JOB 8: Archive WebSocket Cache (Daily at 01:00 WIB)
    # =========================================================================
    async def run_archive_ws_cache_job(
        self, base_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Archive all incoming WebSocket cache log files into date-partitioned .tar.gz archives."""
        try:
            results = await archive_ws_cache(base_path=base_path)
            total_archived = sum(r.get("archived_count", 0) for r in results)
            logger.info(
                "Daily WebSocket cache archive job completed: %d files archived across %d accounts.",
                total_archived,
                len(results),
            )

            # Record audit trail in DB if database session is reachable
            try:
                async with self._get_session() as session:
                    task_repo = container.get_scheduler_task_repo(session)
                    task = await task_repo.get("archive_ws_cache")
                    next_fire = calculate_next_fire_time(task.cron_expr) if task else None
                    await task_repo.record_task_run(
                        task_id="archive_ws_cache",
                        started_at=datetime.now(),
                        finished_at=datetime.now(),
                        status="SUCCESS",
                        next_run_at=next_fire,
                        result_summary={"archived_count": total_archived},
                    )
                    await session.commit()
            except Exception as db_exc:
                logger.debug("Could not record archive_ws_cache audit to DB: %s", db_exc)

            return results
        except Exception as e:
            logger.error("Failed running archive_ws_cache_job: %s", e)
            return []
