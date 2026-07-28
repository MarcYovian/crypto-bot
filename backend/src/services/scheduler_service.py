"""Cron-based background jobs: daily risk snapshot, order cleanup, failsafe sync."""

import logging
from datetime import datetime
from pytz import timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.database.connection import AsyncSessionLocal
from src.repository.trade_repository import TradeRepository
from src.services.execution_engine import BinanceExecutionEngine

logger = logging.getLogger(__name__)
WIB_TZ = timezone("Asia/Jakarta")


class CronSchedulerService:
    """Manages recurring background jobs for bot maintenance.

    Jobs:
    1. **Daily risk snapshot** — captures the USDT balance every midnight (WIB).
    2. **Orphan order cleanup** — cancels limit orders stuck in ``WAITING_ENTRY``
       for more than 4 hours (runs every 30 min).
    3. **Failsafe sync check** — reconciles DB trade status against actual Binance
       positions as a safety net for WebSocket reconnection gaps (runs every 15 min).
    """

    def __init__(self, execution_engine: BinanceExecutionEngine):
        self.scheduler = AsyncIOScheduler(timezone=WIB_TZ)
        self.execution_engine = execution_engine

    def start(self):
        """Register all cron jobs and start the APScheduler instance."""
        # 1. Daily risk snapshot every midnight WIB
        self.scheduler.add_job(
            self._job_daily_risk_snapshot,
            trigger=CronTrigger(hour=0, minute=0, timezone=WIB_TZ),
            id="daily_risk_snapshot",
            replace_existing=True
        )

        # 2. Orphan order cleanup every 30 minutes
        self.scheduler.add_job(
            self._job_cleanup_orphan_orders,
            trigger=CronTrigger(minute="0,30", timezone=WIB_TZ),
            id="cleanup_orphan_orders",
            replace_existing=True
        )

        # 3. Failsafe sync check every 15 minutes (safety net for WS reconnection)
        self.scheduler.add_job(
            self._job_failsafe_sync_check,
            trigger=CronTrigger(minute="15,45", timezone=WIB_TZ),
            id="failsafe_sync_check",
            replace_existing=True
        )

        self.scheduler.start()
        logger.info("Cron Scheduler started (WIB timezone).")

    async def run_initial_daily_risk_check(self):
        """Ensure today's risk snapshot exists when the bot starts; create one if missing."""
        today_str = datetime.now(WIB_TZ).strftime("%Y-%m-%d")
        async with AsyncSessionLocal() as session:
            trade_repo = TradeRepository(session)
            existing = await trade_repo.get_daily_risk(today_str)
            
            if not existing:
                logger.info(f"Daily Risk Snapshot untuk hari ini ({today_str}) belum ada. Membuat snapshot awal...")
                await self._job_daily_risk_snapshot()

    async def _job_daily_risk_snapshot(self):
        """Job 1: Fetch the Futures balance and persist a daily risk snapshot at 00:00 WIB."""
        today_str = datetime.now(WIB_TZ).strftime("%Y-%m-%d")
        logger.info(f"Cron: Daily risk snapshot for {today_str}...")

        try:
            async with AsyncSessionLocal() as session:
                trade_repo = TradeRepository(session)
                
                existing = await trade_repo.get_daily_risk(today_str)
                if existing:
                    logger.info(f"Risk snapshot for {today_str} already exists (Balance: ${existing.balance:.2f}, Risk Amount: ${existing.risk_amount:.2f}). Skipping.")
                    return

                balance_data = await self.execution_engine.fetch_balance()
                usdt_balance = float(balance_data.get('USDT', {}).get('total', 0.0))

                if usdt_balance <= 0:
                    logger.error("Failed to fetch Binance balance or USDT balance <= 0.")
                    return

                risk_pct = 2.0
                snapshot = await trade_repo.create_daily_risk_snapshot(
                    date_str=today_str,
                    balance=usdt_balance,
                    risk_percent=risk_pct
                )
                logger.info(f"Daily risk snapshot saved! Balance: ${snapshot.balance:.2f} | Risk Amount: ${snapshot.risk_amount:.2f}")

        except Exception as e:
            logger.error(f"Cron daily risk snapshot error: {str(e)}")

    async def _job_cleanup_orphan_orders(self):
        """Job 2: Cancel limit orders stuck in ``WAITING_ENTRY`` for more than 4 hours.

        This is appropriate for 15M / 1H signal timeframes.
        """
        logger.debug("Cron: Checking expired limit orders (> 4h)...")
        try:
            async with AsyncSessionLocal() as session:
                trade_repo = TradeRepository(session)
                expired_trades = await trade_repo.get_expired_waiting_trades(max_hours=4)

                for trade in expired_trades:
                    logger.info(f"Trade #{trade.id} ({trade.symbol}) WAITING_ENTRY > 4h. Cancelling limit order...")
                    try:
                        await self.execution_engine.cancel_all_orders(trade.symbol)
                    except Exception as err:
                        logger.warning(f"Warning cancelling order [{trade.symbol}]: {err}")

                    await trade_repo.update_trade_status(trade.id, "CANCELLED")
                    await trade_repo.log_event(trade.id, "FORCE_CLOSE", payload_json='{"reason": "EXPIRED_LIMIT_4H"}')

        except Exception as e:
            logger.error(f"Cron orphan order cleanup error: {str(e)}")

    async def _job_failsafe_sync_check(self):
        """Job 3: Reconcile DB trade status with actual Binance positions.

        Acts as a safety net when the WebSocket has been disconnected:
        - ``WAITING_ENTRY`` with a non-zero Binance position → mark ``OPEN``.
        - ``OPEN`` / ``PARTIAL`` with a zero Binance position → mark ``CLOSED``.
        """
        logger.debug("Cron: Failsafe sync check with Binance...")
        try:
            async with AsyncSessionLocal() as session:
                trade_repo = TradeRepository(session)
                active_trades = await trade_repo.get_active_trades()

                for trade in active_trades:
                    # Ambil informasi posisi terbuka dari Binance Futures via execution_engine
                    positions = await self.execution_engine.fetch_positions([trade.symbol])
                    pos = next((p for p in positions if p.get('symbol') == trade.symbol), None)

                    position_qty = abs(float(pos.get('contracts') or pos.get('positionAmt') or 0.0)) if pos else 0.0

                    if trade.status == "WAITING_ENTRY" and position_qty > 0:
                        logger.info(f"[Failsafe Sync] Limit #{trade.id} ({trade.symbol}) FILLED on Binance. Syncing DB -> OPEN.")
                        await trade_repo.update_trade_status(trade.id, "OPEN")
                        await trade_repo.log_event(trade.id, "FAILSAFE_SYNC", f'{{"status": "OPEN", "qty": {position_qty}}}')

                    elif trade.status in ["OPEN", "PARTIAL"] and position_qty == 0:
                        logger.info(f"[Failsafe Sync] Trade #{trade.id} ({trade.symbol}) CLOSED on Binance. Syncing DB -> CLOSED.")
                        await trade_repo.update_trade_status(trade.id, "CLOSED", closed_at=datetime.now())
                        await trade_repo.log_event(trade.id, "FAILSAFE_SYNC", '{"status": "CLOSED"}')

        except Exception as e:
            logger.error(f"Cron failsafe sync check error: {str(e)}")

    def stop(self):
        """Shut down the scheduler."""
        self.scheduler.shutdown()
        logger.info("Cron Scheduler stopped.")