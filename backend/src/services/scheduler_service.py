"""Automated background scheduler service for risk management, order maintenance, and system health."""

import json
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pytz import timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.schemas.risk import DailyRiskConfigCreate
from src.schemas.trade import TradeStatusUpdate
from src.schemas.master import InstrumentCreate
from src.schemas.system import BotLogCreate
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.trading_account_repository import TradingAccountRepository
from src.repository.risk_profile_repository import RiskProfileRepository
from src.repository.trade_repository import TradeRepository
from src.repository.order_repository import OrderRepository
from src.repository.instrument_repository import InstrumentRepository
from src.repository.trade_summary_repository import TradeSummaryRepository
from src.repository.trade_event_repository import TradeEventRepository
from src.repository.bot_log_repository import BotLogRepository
from src.repository.bot_setting_repository import BotSettingRepository
from src.services.position_manager import PositionManager
from src.services.instrument_service import InstrumentService
from src.clients.binance_client import BinanceRestClient
from src.clients.telegram_client import TelegramNotifierClient

logger = logging.getLogger(__name__)
WIB_TZ = timezone("Asia/Jakarta")


class SchedulerService:
    """Orchestrates 7 background cron and recurring maintenance jobs for the trading system."""

    def __init__(
        self,
        daily_risk_repo: DailyRiskRepository,
        trading_account_repo: TradingAccountRepository,
        risk_profile_repo: RiskProfileRepository,
        trade_repo: TradeRepository,
        order_repo: OrderRepository,
        instrument_repo: InstrumentRepository,
        trade_summary_repo: TradeSummaryRepository,
        trade_event_repo: TradeEventRepository,
        bot_log_repo: BotLogRepository,
        bot_setting_repo: BotSettingRepository,
        position_manager: Optional[PositionManager] = None,
        instrument_service: Optional[InstrumentService] = None,
        binance_client: Optional[BinanceRestClient] = None,
        telegram_client: Optional[TelegramNotifierClient] = None,
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
        self.binance_client = binance_client
        self.telegram_client = telegram_client

        self.scheduler = AsyncIOScheduler(timezone=WIB_TZ)

    def start(self) -> None:
        """Register all 7 cron jobs and start APScheduler."""
        # 1. Daily Risk Snapshot at 00:00 WIB
        self.scheduler.add_job(
            self.run_daily_risk_snapshot_job,
            trigger=CronTrigger(hour=0, minute=0, timezone=WIB_TZ),
            id="daily_risk_snapshot",
            replace_existing=True,
        )

        # 2. Cleanup Orphan Orders every 30 minutes
        self.scheduler.add_job(
            self.run_cleanup_orphan_orders_job,
            trigger=CronTrigger(minute="0,30", timezone=WIB_TZ),
            id="cleanup_orphan_orders",
            replace_existing=True,
        )

        # 3. Failsafe Sync Check every 15 minutes
        self.scheduler.add_job(
            self.run_failsafe_sync_job,
            trigger=CronTrigger(minute="15,45", timezone=WIB_TZ),
            id="failsafe_sync_check",
            replace_existing=True,
        )

        # 4. Sync Instruments Metadata every 12 hours (06:00 & 18:00 WIB)
        self.scheduler.add_job(
            self.run_sync_instruments_metadata_job,
            trigger=CronTrigger(hour="6,18", minute=0, timezone=WIB_TZ),
            id="sync_instruments_metadata",
            replace_existing=True,
        )

        # 5. Purge Old Logs daily at 03:00 WIB
        self.scheduler.add_job(
            self.run_purge_old_logs_job,
            trigger=CronTrigger(hour=3, minute=0, timezone=WIB_TZ),
            id="purge_old_logs",
            replace_existing=True,
        )

        # 6. Daily Performance Report at 00:05 WIB
        self.scheduler.add_job(
            self.run_daily_performance_report_job,
            trigger=CronTrigger(hour=0, minute=5, timezone=WIB_TZ),
            id="daily_performance_report",
            replace_existing=True,
        )

        # 7. Heartbeat Health Check every hour
        self.scheduler.add_job(
            self.run_heartbeat_health_check_job,
            trigger=CronTrigger(minute=0, timezone=WIB_TZ),
            id="heartbeat_health_check",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info("SchedulerService started with 7 recurring maintenance jobs.")

    def stop(self) -> None:
        """Shutdown APScheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("SchedulerService stopped.")

    # =========================================================================
    # JOB 1: Daily Risk Snapshot (00:00 WIB)
    # =========================================================================
    async def run_daily_risk_snapshot_job(
        self, account_id: int = 1, snapshot_date: Optional[date] = None
    ) -> Any:
        """Lock initial balance at midnight and compute daily risk budget."""
        target_date = snapshot_date or datetime.now(WIB_TZ).date()

        # 1. Fetch balance from Binance
        balance = Decimal("10000.0")
        if self.binance_client:
            try:
                bal_data = await self.binance_client.fetch_balance()
                balance = bal_data.get("total_wallet_balance") or bal_data.get("free_margin") or Decimal("10000.0")
            except Exception as e:
                logger.error(f"Failed to fetch balance from Binance during snapshot: {e}")

        # 2. Get active risk profile
        profile = await self.risk_profile_repo.get_active_profile()
        profile_id = profile.id if profile else 1
        loss_limit_pct = Decimal("2.0")  # default 2%

        # 3. Calculate max daily loss budget in USDT
        daily_risk_budget = balance * (loss_limit_pct / Decimal("100"))

        # 4. Save idempotent snapshot
        snapshot = await self.daily_risk_repo.get_or_create_daily_snapshot(
            DailyRiskConfigCreate(
                account_id=account_id,
                risk_profile_id=profile_id,
                date=target_date,
                balance=balance,
                risk_amount=daily_risk_budget,
            )
        )

        # 5. Reset Circuit Breaker and Auto-Unpause for the new day
        if self.bot_setting_repo:
            try:
                await self.bot_setting_repo.set_value("is_paused", "false")
                await self.bot_setting_repo.set_value("trading_status", "ACTIVE")
            except Exception:
                pass

        # 6. Broadcast to Telegram
        if self.telegram_client:
            try:
                msg = (
                    f"🌅 <b>DAILY RISK SNAPSHOT (00:00 WIB)</b>\n"
                    f"📅 Tanggal: <code>{target_date.isoformat()}</code>\n"
                    f"💰 Saldo Modal Awal: <b>${balance:,.2f} USDT</b>\n"
                    f"🛡️ Anggaran Risiko (2%): <b>${daily_risk_budget:,.2f} USDT</b>\n"
                    f"✅ Circuit Breaker: <b>ACTIVE & READY</b>"
                )
                await self.telegram_client.send_message(chat_id="ADMIN_CHANNEL", text=msg)
            except Exception as e:
                logger.error(f"Failed to send snapshot alert to Telegram: {e}")

        return snapshot

    # =========================================================================
    # JOB 2: Cleanup Orphan Orders (Every 30 Minutes)
    # =========================================================================
    async def run_cleanup_orphan_orders_job(
        self, account_id: int = 1, max_age_hours: int = 4
    ) -> int:
        """Cancel pending WAITING_ENTRY limit orders older than max_age_hours."""
        expired_trades = await self.trade_repo.get_expired_waiting_trades(
            max_hours=max_age_hours
        )
        cancelled_count = 0

        for trade in expired_trades:
            if trade.account_id != account_id:
                continue

            # 1. Cancel Binance open orders
            if self.binance_client:
                instrument = await self.instrument_repo.get(trade.instrument_id)
                if instrument:
                    try:
                        await self.binance_client.cancel_all_orders(symbol=instrument.symbol)
                    except Exception as e:
                        logger.error(f"Failed to cancel exchange orders for trade {trade.id}: {e}")

            # 2. Cancel DB open orders
            await self.order_repo.cancel_all_open_orders_for_trade(trade.id)

            # 3. Update trade status to CANCELLED
            await self.trade_repo.update_trade_status(
                trade_id=trade.id,
                schema=TradeStatusUpdate(status="CANCELLED", closed_at=datetime.now()),
            )

            # 4. Log trade event
            await self.trade_event_repo.log_event(
                trade_id=trade.id,
                event_type="ORDER_ERROR",
                payload={"reason": "ORPHAN_ORDER_TIMEOUT", "max_age_hours": max_age_hours},
            )
            cancelled_count += 1

        if cancelled_count > 0:
            logger.info(f"Cleaned up {cancelled_count} orphan WAITING_ENTRY trades.")
        return cancelled_count

    # =========================================================================
    # JOB 3: Failsafe Sync Check (Every 15 Minutes)
    # =========================================================================
    async def run_failsafe_sync_job(self, account_id: int = 1) -> Dict[str, Any]:
        """Reconcile database active trades with live Binance open positions."""
        active_trades = await self.trade_repo.get_all_active_trades(account_id=account_id)
        positions_map: Dict[str, Decimal] = {}

        if self.binance_client:
            try:
                live_positions = await self.binance_client.fetch_positions()
                for pos in live_positions:
                    sym = str(pos.get("symbol", "")).upper().replace("/", "").split(":")[0]
                    size = Decimal(str(pos.get("contracts", 0.0)))
                    positions_map[sym] = size
            except Exception as e:
                logger.error(f"Failsafe sync: Failed to fetch Binance positions: {e}")

        desynced_closed = 0
        for trade in active_trades:
            instrument = await self.instrument_repo.get(trade.instrument_id)
            if not instrument:
                continue

            inst_sym = instrument.symbol.upper().replace("/", "").split(":")[0]
            live_qty = positions_map.get(inst_sym, Decimal("0.0"))

            # If position is closed on Binance but still open in DB
            if live_qty == Decimal("0.0") and trade.status in ("OPEN", "PARTIAL"):
                if self.position_manager:
                    await self.position_manager.finalize_trade_closure(
                        trade_id=trade.id, close_reason="FAILSAFE_SYNC"
                    )
                else:
                    await self.trade_repo.update_trade_status(
                        trade_id=trade.id,
                        schema=TradeStatusUpdate(status="CLOSED", closed_at=datetime.now()),
                    )
                desynced_closed += 1

        return {
            "total_checked": len(active_trades),
            "desynced_closed": desynced_closed,
            "timestamp": datetime.now().isoformat(),
        }

    # =========================================================================
    # JOB 4: Sync Instruments Metadata (Every 12 Hours)
    # =========================================================================
    async def run_sync_instruments_metadata_job(self, exchange_id: int = 1) -> int:
        """Fetch updated symbol filters from Binance and bulk-upsert into instruments table."""
        if self.instrument_service:
            return await self.instrument_service.sync_all_instruments(exchange_id=exchange_id)

        if not self.binance_client:
            return 0

        try:
            metadata_list = await self.binance_client.fetch_instruments_metadata()
            schemas: List[InstrumentCreate] = []

            for item in metadata_list:
                schemas.append(
                    InstrumentCreate(
                        exchange_id=exchange_id,
                        symbol=item["symbol"],
                        base_asset=item.get("base_asset", item["symbol"].replace("USDT", "")),
                        quote_asset=item.get("quote_asset", "USDT"),
                        tick_size=Decimal(str(item.get("tick_size", "0.1"))),
                        step_size=Decimal(str(item.get("step_size", "0.001"))),
                        min_qty=Decimal(str(item.get("min_qty", "0.001"))),
                        min_notional=Decimal(str(item.get("min_notional", "5.0"))),
                        price_precision=int(item.get("price_precision", 2)),
                        qty_precision=int(item.get("qty_precision", 3)),
                        is_active=True,
                    )
                )

            count = await self.instrument_repo.bulk_upsert_instruments(schemas)
            logger.info(f"Synced {count} instrument metadata records from Binance.")
            return count
        except Exception as e:
            logger.error(f"Failed to sync instrument metadata: {e}")
            return 0

    # =========================================================================
    # JOB 5: Purge Old Logs (Daily at 03:00 WIB)
    # =========================================================================
    async def run_purge_old_logs_job(self, days: int = 30) -> int:
        """Purge system logs older than retention days."""
        deleted_count = await self.bot_log_repo.purge_old_logs(days=days)
        logger.info(f"Purged {deleted_count} system logs older than {days} days.")
        return deleted_count

    # =========================================================================
    # JOB 6: Daily Performance Report (00:05 WIB)
    # =========================================================================
    async def run_daily_performance_report_job(self, account_id: int = 1) -> Dict[str, Any]:
        """Aggregate yesterday's closed trades and send daily performance report to Telegram."""
        yesterday_end = datetime.now()
        yesterday_start = yesterday_end - timedelta(days=1)

        perf = await self.trade_summary_repo.get_performance_summary(
            account_id=account_id,
            start_date=yesterday_start,
            end_date=yesterday_end,
        )

        total_trades = perf["total_trades"]
        wins = perf["winning_trades"]
        losses = perf["losing_trades"]
        total_pnl = perf["total_net_pnl"]
        win_rate = perf["win_rate"]

        if self.telegram_client:
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
                await self.telegram_client.send_message(chat_id="ADMIN_CHANNEL", text=msg)
            except Exception as e:
                logger.error(f"Failed to send daily performance report: {e}")

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
        db_healthy = True
        binance_healthy = True

        # 1. Check DB query
        try:
            await self.bot_setting_repo.get_all_as_dict()
        except Exception:
            db_healthy = False

        # 2. Check Binance API liveness
        if self.binance_client:
            try:
                await self.binance_client.fetch_balance()
            except Exception:
                binance_healthy = False

        is_healthy = db_healthy and binance_healthy
        level = "INFO" if is_healthy else "ERROR"

        await self.bot_log_repo.create(
            BotLogCreate(
                level=level,
                module="SchedulerService",
                message="Hourly Heartbeat Health Check",
                context_json=json.dumps({
                    "db_healthy": db_healthy,
                    "binance_healthy": binance_healthy,
                    "is_healthy": is_healthy,
                }),
            )
        )

        return {
            "db_healthy": db_healthy,
            "binance_healthy": binance_healthy,
            "is_healthy": is_healthy,
            "timestamp": datetime.now().isoformat(),
        }