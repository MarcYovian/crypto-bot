"""Automated background scheduler service for risk management, order maintenance, and system health."""

import json
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, AsyncIterator, Dict, List, Optional
from pytz import timezone
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.persistence.connection import AsyncSessionLocal
from src.infrastructure.di.container import container
from src.domain.ports.gateways import IExchangeGateway, INotificationGateway
from src.infrastructure.persistence.repositories.bot_log_repository import BotLogRepository
from src.infrastructure.persistence.repositories.bot_setting_repository import BotSettingRepository
from src.infrastructure.persistence.repositories.daily_risk_repository import DailyRiskRepository
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.order_repository import OrderRepository
from src.infrastructure.persistence.repositories.risk_profile_repository import RiskProfileRepository
from src.infrastructure.persistence.repositories.trade_event_repository import TradeEventRepository
from src.infrastructure.persistence.repositories.trade_repository import TradeRepository
from src.infrastructure.persistence.repositories.trade_summary_repository import TradeSummaryRepository
from src.infrastructure.persistence.repositories.trading_account_repository import TradingAccountRepository
from src.presentation.api.schemas.system import BotLogCreate
from src.presentation.api.schemas.trade import TradeStatusUpdate
from src.presentation.api.schemas.event_summary import TradeSummaryCreate
from src.application.use_cases.risk.daily_risk_snapshot_use_case import DailyRiskSnapshotUseCase
from src.application.use_cases.trades.cleanup_orphan_orders_use_case import CleanupOrphanOrdersUseCase
from src.application.use_cases.instruments.sync_instruments_use_case import SyncInstrumentsUseCase
from src.utils.ws_cache_logger import archive_ws_cache


logger = logging.getLogger(__name__)
WIB_TZ = timezone("Asia/Jakarta")


class SchedulerJobs:
    """Encapsulates execution logic and repository interactions for recurring maintenance tasks."""

    def __init__(
        self,
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
        self.daily_risk_repo = daily_risk_repo
        self.trading_account_repo = trading_account_repo
        self.risk_profile_repo = risk_profile_repo
        self.trade_repo = trade_repo
        self.order_repo = order_repo
        self.instrument_repo = instrument_repo
        self.trade_summary_repo = trade_summary_repo
        self.trade_event_repo = trade_event_repo
        self.bot_log_repo = bot_log_repo
        self.bot_setting_repo = bot_setting_repo
        self.position_manager = position_manager
        self.instrument_service = instrument_service
        self.exchange_gateway = exchange_gateway
        self.notification_gateway = notification_gateway
        self.session_factory = session_factory or AsyncSessionLocal

    @asynccontextmanager
    async def _get_session(self) -> AsyncIterator[AsyncSession]:
        """Provide a scoped database session per job execution."""
        existing_session = None
        for repo in (
            self.daily_risk_repo,
            self.trade_repo,
            self.order_repo,
            self.instrument_repo,
            self.bot_log_repo,
            self.bot_setting_repo,
        ):
            if repo and hasattr(repo, "session") and repo.session:
                existing_session = repo.session
                break

        if existing_session is not None:
            yield existing_session
        else:
            factory = self.session_factory or AsyncSessionLocal
            async with factory() as session:
                try:
                    yield session
                except Exception:
                    await session.rollback()
                    raise

    # =========================================================================
    # JOB 1: Daily Risk Snapshot (00:00 WIB)
    # =========================================================================
    async def run_daily_risk_snapshot_job(
        self, account_id: int = 1, snapshot_date: Optional[date] = None
    ) -> Any:
        """Lock initial balance at midnight and compute daily risk budget via DailyRiskSnapshotUseCase."""
        async with self._get_session() as session:
            daily_risk_repo = self.daily_risk_repo or DailyRiskRepository(session)
            risk_profile_repo = self.risk_profile_repo or RiskProfileRepository(session)
            bot_setting_repo = self.bot_setting_repo or BotSettingRepository(session)
            exchange_gateway = self.exchange_gateway or container.exchange_gateway
            notification_gateway = self.notification_gateway or container.notification_gateway

            use_case = DailyRiskSnapshotUseCase(
                daily_risk_repo=daily_risk_repo,
                risk_profile_repo=risk_profile_repo,
                bot_setting_repo=bot_setting_repo,
                exchange_gateway=exchange_gateway,
                notification_gateway=notification_gateway,
            )
            snapshot = await use_case.execute(account_id=account_id, snapshot_date=snapshot_date)
            await session.commit()
            return snapshot

    # =========================================================================
    # JOB 2: Cleanup Orphan Orders (Every 30 Minutes)
    # =========================================================================
    async def run_cleanup_orphan_orders_job(
        self, account_id: int = 1, max_age_hours: int = 4
    ) -> int:
        """Cancel pending WAITING_ENTRY limit orders older than max_age_hours via CleanupOrphanOrdersUseCase."""
        async with self._get_session() as session:
            trade_repo = self.trade_repo or TradeRepository(session)
            order_repo = self.order_repo or OrderRepository(session)
            instrument_repo = self.instrument_repo or InstrumentRepository(session)
            trade_event_repo = self.trade_event_repo or TradeEventRepository(session)
            exchange_gateway = self.exchange_gateway or container.exchange_gateway

            use_case = CleanupOrphanOrdersUseCase(
                trade_repo=trade_repo,
                order_repo=order_repo,
                instrument_repo=instrument_repo,
                trade_event_repo=trade_event_repo,
                exchange_gateway=exchange_gateway,
            )
            cancelled_count = await use_case.execute(account_id=account_id, max_age_hours=max_age_hours)
            await session.commit()
            return cancelled_count

    # =========================================================================
    # JOB 3: Failsafe Sync Check (Every 15 Minutes)
    # =========================================================================
    async def run_failsafe_sync_job(self, account_id: int = 1) -> Dict[str, Any]:
        """Reconcile database active trades with live exchange open positions."""
        async with self._get_session() as session:
            trade_repo = self.trade_repo or TradeRepository(session)
            instrument_repo = self.instrument_repo or InstrumentRepository(session)
            client = self.exchange_gateway or container.exchange_gateway

            active_trades = await trade_repo.get_all_active_trades(account_id=account_id)
            positions_map: Dict[str, Decimal] = {}

            if client:
                try:
                    live_positions = await client.fetch_positions()
                    for pos in live_positions:
                        sym = str(pos.get("symbol", "")).upper().replace("/", "").split(":")[0]
                        size = Decimal(str(pos.get("contracts") or pos.get("size") or 0.0))
                        positions_map[sym] = size
                except Exception as e:
                    logger.error("Failsafe sync: Failed to fetch exchange positions: %s", e)

            desynced_closed = 0
            for trade in active_trades:
                instrument = await instrument_repo.get(trade.instrument_id)
                if not instrument:
                    continue

                inst_sym = instrument.symbol.upper().replace("/", "").split(":")[0]
                live_qty = positions_map.get(inst_sym, Decimal("0.0"))

                # If position is closed on exchange but still open in DB
                if live_qty == Decimal("0.0") and trade.status in ("OPEN", "PARTIAL"):
                    if self.position_manager and hasattr(self.position_manager, "finalize_trade_closure"):
                        await self.position_manager.finalize_trade_closure(
                            trade_id=trade.id, close_reason="FAILSAFE_SYNC"
                        )
                    else:
                        await trade_repo.update_partial_close(
                            trade_id=trade.id,
                            closed_qty=trade.remaining_qty or trade.position_size,
                        )
                        await trade_repo.update_trade_status(
                            trade_id=trade.id,
                            schema=TradeStatusUpdate(status="CLOSED", closed_at=datetime.now()),
                        )
                        if self.trade_summary_repo:
                            await self.trade_summary_repo.create(
                                TradeSummaryCreate(
                                    trade_id=trade.id,
                                    gross_pnl=Decimal("0.0"),
                                    net_pnl=Decimal("0.0"),
                                    commission=Decimal("0.0"),
                                    funding=Decimal("0.0"),
                                    roi=Decimal("0.0"),
                                    rr=Decimal("0.0"),
                                    result="BREAKEVEN",
                                    duration_seconds=0,
                                    close_reason="FAILSAFE_SYNC",
                                    closed_at=datetime.now(),
                                )
                            )
                    desynced_closed += 1

            await session.commit()
            return {
                "total_checked": len(active_trades),
                "desynced_closed": desynced_closed,
                "timestamp": datetime.now().isoformat(),
            }

    # =========================================================================
    # JOB 4: Sync Instruments Metadata (Every 12 Hours)
    # =========================================================================
    async def run_sync_instruments_metadata_job(self, exchange_id: int = 1) -> int:
        """Fetch updated symbol filters from exchange and bulk-upsert into instruments table."""
        if self.instrument_service and hasattr(self.instrument_service, "sync_all_instruments"):
            return await self.instrument_service.sync_all_instruments(exchange_id=exchange_id)

        async with self._get_session() as session:
            instrument_repo = self.instrument_repo or InstrumentRepository(session)
            exchange_repo = ExchangeRepository(session)
            exchange_gateway = self.exchange_gateway or container.exchange_gateway

            use_case = SyncInstrumentsUseCase(
                instrument_repo=instrument_repo,
                exchange_repo=exchange_repo,
                exchange_gateway=exchange_gateway,
            )
            count = await use_case.sync_all_instruments(exchange_id=exchange_id)
            await session.commit()
            return count

    # =========================================================================
    # JOB 5: Purge Old Logs (Daily at 03:00 WIB)
    # =========================================================================
    async def run_purge_old_logs_job(self, days: int = 30) -> int:
        """Purge system logs older than retention days."""
        async with self._get_session() as session:
            bot_log_repo = self.bot_log_repo or BotLogRepository(session)
            deleted_count = await bot_log_repo.purge_old_logs(days=days)
            await session.commit()
            logger.info("Purged %d system logs older than %d days.", deleted_count, days)
            return deleted_count

    # =========================================================================
    # JOB 6: Daily Performance Report (00:05 WIB)
    # =========================================================================
    async def run_daily_performance_report_job(self, account_id: int = 1) -> Dict[str, Any]:
        """Aggregate yesterday's closed trades and send daily performance report to Telegram."""
        async with self._get_session() as session:
            trade_summary_repo = self.trade_summary_repo or TradeSummaryRepository(session)
            notifier = self.notification_gateway or container.notification_gateway

            yesterday_end = datetime.now()
            yesterday_start = yesterday_end - timedelta(days=1)

            perf = await trade_summary_repo.get_performance_summary(
                account_id=account_id,
                start_date=yesterday_start,
                end_date=yesterday_end,
            )

            total_trades = perf["total_trades"]
            wins = perf["winning_trades"]
            losses = perf["losing_trades"]
            total_pnl = perf["total_net_pnl"]
            win_rate = perf["win_rate"]

            if notifier:
                try:
                    pnl_icon = "🟢" if total_pnl >= Decimal("0") else "🔴"
                    msg = (
                        f"📊 <b>DAILY TRADING RECAP REPORT</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"📈 Total Trades Selesai: <b>{total_trades}</b>\n"
                        f"🏆 Win: <b>{wins}</b> | 🛑 Loss: <b>{losses}</b>\n"
                        f"🎯 Win Rate: <b>{win_rate}%</b>\n"
                        f"{pnl_icon} Net Realized PnL: <b>${total_pnl:+,.2f} USDT</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━"
                    )
                    await notifier.send_message(chat_id="ADMIN_CHANNEL", text=msg)
                except Exception as e:
                    logger.error("Failed to send daily performance report: %s", e)

            return {
                "total_trades": total_trades,
                "wins": wins,
                "losses": losses,
                "win_rate": float(win_rate),
                "net_pnl": float(total_pnl),
            }

    # =========================================================================
    # JOB 7: Heartbeat Health Check (Every 1 Hour)
    # =========================================================================
    async def run_heartbeat_health_check_job(self) -> Dict[str, Any]:
        """Perform system-wide health check and record log audit."""
        async with self._get_session() as session:
            bot_setting_repo = self.bot_setting_repo or BotSettingRepository(session)
            bot_log_repo = self.bot_log_repo or BotLogRepository(session)
            client = self.exchange_gateway or container.exchange_gateway

            db_healthy = True
            exchange_healthy = True

            # 1. Check DB query
            try:
                await bot_setting_repo.get_all_as_dict()
            except Exception:
                db_healthy = False

            # 2. Check exchange API liveness
            if client:
                try:
                    await client.fetch_balance()
                except Exception:
                    exchange_healthy = False

            is_healthy = db_healthy and exchange_healthy
            level = "INFO" if is_healthy else "ERROR"

            context_dict = {
                "db_healthy": db_healthy,
                "exchange_healthy": exchange_healthy,
                "is_healthy": is_healthy,
            }

            await bot_log_repo.create(
                BotLogCreate(
                    level=level,
                    module="SchedulerService",
                    message="Hourly Heartbeat Health Check",
                    context_json=json.dumps(context_dict),
                )
            )
            await session.commit()

            return {
                **context_dict,
                "timestamp": datetime.now().isoformat(),
            }

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
            return results
        except Exception as e:
            logger.error("Failed running archive_ws_cache_job: %s", e)
            return []
