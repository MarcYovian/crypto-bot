"""Scheduler lifecycle manager for APScheduler background recurring jobs."""

import logging
from typing import Any, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.ports.gateways import INotificationGateway
from src.infrastructure.persistence.repositories.bot_log_repository import BotLogRepository
from src.infrastructure.persistence.repositories.bot_setting_repository import BotSettingRepository
from src.infrastructure.persistence.repositories.daily_risk_repository import DailyRiskRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.order_repository import OrderRepository
from src.infrastructure.persistence.repositories.risk_profile_repository import RiskProfileRepository
from src.infrastructure.persistence.repositories.trade_event_repository import TradeEventRepository
from src.infrastructure.persistence.repositories.trade_repository import TradeRepository
from src.infrastructure.persistence.repositories.trade_summary_repository import TradeSummaryRepository
from src.infrastructure.persistence.repositories.trading_account_repository import TradingAccountRepository
from src.infrastructure.scheduler.jobs import SchedulerJobs, WIB_TZ

logger = logging.getLogger(__name__)


class SchedulerRunner:
    """Lifecycle manager for automated risk management, order maintenance, and system health jobs."""

    def __init__(
        self,
        jobs: Optional[SchedulerJobs] = None,
        daily_risk_repo: Optional[DailyRiskRepository] = None,
        trading_account_repo: Optional[TradingAccountRepository] = None,
        risk_profile_repo: Optional[RiskProfileRepository] = None,
        trade_repo: Optional[TradeRepository] = None,
        order_repo: Optional[OrderRepository] = None,
        instrument_repo: Optional[InstrumentRepository] = None,
        trade_summary_repo: Optional[TradeSummaryRepository] = None,
        trade_event_repo: Optional[TradeEventRepository] = None,
        bot_log_repo: Optional[BotLogRepository] = None,
        bot_setting_repo: Optional[BotSettingRepository] = None,
        position_manager: Optional[Any] = None,
        instrument_service: Optional[Any] = None,
        exchange_gateway: Optional[Any] = None,
        notification_gateway: Optional[INotificationGateway] = None,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self.jobs = jobs or SchedulerJobs(
            daily_risk_repo=daily_risk_repo,
            trading_account_repo=trading_account_repo,
            risk_profile_repo=risk_profile_repo,
            trade_repo=trade_repo,
            order_repo=order_repo,
            instrument_repo=instrument_repo,
            trade_summary_repo=trade_summary_repo,
            trade_event_repo=trade_event_repo,
            bot_log_repo=bot_log_repo,
            bot_setting_repo=bot_setting_repo,
            position_manager=position_manager,
            instrument_service=instrument_service,
            exchange_gateway=exchange_gateway,
            notification_gateway=notification_gateway,
            session_factory=session_factory,
        )
        self.scheduler = AsyncIOScheduler(timezone=WIB_TZ)

    def __getattr__(self, name: str) -> Any:
        """Delegate job execution methods to the internal SchedulerJobs instance."""
        return getattr(self.jobs, name)

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
