# src/services/scheduler_service.py
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
    """
    Service pengelola Cron Job teratur:
    1. Daily Risk Snapshot (00:00 WIB)
    2. Orphan / Expired Limit Orders Cleanup (> 4 Jam)
    3. Failsafe Sync Check (Jaring Pengaman jika WebSocket sempat Reconnect)
    """

    def __init__(self, execution_engine: BinanceExecutionEngine):
        self.scheduler = AsyncIOScheduler(timezone=WIB_TZ)
        self.execution_engine = execution_engine

    def start(self):
        """Mendaftarkan task scheduler dan memulainya."""
        # 1. Daily Risk Snapshot - Setiap Jam 00:00 WIB
        self.scheduler.add_job(
            self._job_daily_risk_snapshot,
            trigger=CronTrigger(hour=0, minute=0, timezone=WIB_TZ),
            id="daily_risk_snapshot",
            replace_existing=True
        )

        # 2. Cleanup Orphan / Expired Limit Orders - Setiap 30 Menit
        self.scheduler.add_job(
            self._job_cleanup_orphan_orders,
            trigger=CronTrigger(minute="0,30", timezone=WIB_TZ),
            id="cleanup_orphan_orders",
            replace_existing=True
        )

        # 3. Failsafe Sync Check - Setiap 15 Menit (Safety Net WebSocket Reconnect)
        self.scheduler.add_job(
            self._job_failsafe_sync_check,
            trigger=CronTrigger(minute="15,45", timezone=WIB_TZ),
            id="failsafe_sync_check",
            replace_existing=True
        )

        self.scheduler.start()
        logger.info("⏰ Cron Scheduler Engine Berhasil Dijalankan (WIB Zone)!")

    async def run_initial_daily_risk_check(self):
        """
        Fungsi helper yang dipanggil saat startup bot:
        Memastikan snapshot risk hari ini sudah ada, jika belum -> buat sekarang.
        """
        today_str = datetime.now(WIB_TZ).strftime("%Y-%m-%d")
        async with AsyncSessionLocal() as session:
            trade_repo = TradeRepository(session)
            existing = await trade_repo.get_daily_risk(today_str)
            
            if not existing:
                logger.info(f"Daily Risk Snapshot untuk hari ini ({today_str}) belum ada. Membuat snapshot awal...")
                await self._job_daily_risk_snapshot()

    async def _job_daily_risk_snapshot(self):
        """CRON 1: Mengambil balance Futures dan menyimpan Snapshot Risk 00:00 WIB."""
        today_str = datetime.now(WIB_TZ).strftime("%Y-%m-%d")
        logger.info(f"Executing Cron: Daily Risk Snapshot untuk tanggal {today_str}...")

        try:
            async with AsyncSessionLocal() as session:
                trade_repo = TradeRepository(session)
                
                # Check Guard: Jika snapshot hari ini sudah ada, lewati agar tidak error constraint
                existing = await trade_repo.get_daily_risk(today_str)
                if existing:
                    logger.info(f"Snapshot risk untuk {today_str} sudah ada (Balance: ${existing.balance:.2f}). Skipping.")
                    return

                # Ambil saldo akun Futures via CCXT API
                balance_data = await self.execution_engine.fetch_balance()
                usdt_balance = float(balance_data.get('USDT', {}).get('total', 0.0))

                if usdt_balance <= 0:
                    logger.error("Gagal mengambil saldo Binance atau saldo USDT <= 0.")
                    return

                risk_pct = 2.0  # Risk 2% per trade
                snapshot = await trade_repo.create_daily_risk_snapshot(
                    date_str=today_str,
                    balance=usdt_balance,
                    risk_percent=risk_pct
                )
                logger.info(f"✅ Daily Risk Snapshot Saved! Balance: ${snapshot.balance:.2f} | Risk Amount: ${snapshot.risk_amount:.2f}")

        except Exception as e:
            logger.error(f"Error pada Cron Daily Risk Snapshot: {str(e)}")

    async def _job_cleanup_orphan_orders(self):
        """
        CRON 2: Menghapus order LIMIT gantung (WAITING_ENTRY) yang umurnya > 4 jam
        (Sangat pas untuk timeframe sinyal 15M / 1H).
        """
        logger.debug("Executing Cron: Checking Expired Limit Orders (> 4 Jam)...")
        try:
            async with AsyncSessionLocal() as session:
                trade_repo = TradeRepository(session)
                expired_trades = await trade_repo.get_expired_waiting_trades(max_hours=4)

                for trade in expired_trades:
                    logger.info(f"🧹 Trade #{trade.id} ({trade.symbol}) berstatus WAITING_ENTRY > 4 jam. Membatalkan order Limit...")
                    
                    # 1. Batalkan semua order gantung untuk koin ini di Binance
                    try:
                        await self.execution_engine.exchange.cancel_all_orders(trade.symbol)
                    except Exception as err:
                        logger.warning(f"Warning cancel order Binance [{trade.symbol}]: {err}")

                    # 2. Update status trade di DB menjadi CANCELLED (EXPIRED)
                    await trade_repo.update_trade_status(trade.id, "CANCELLED")
                    await trade_repo.log_event(trade.id, "FORCE_CLOSE", payload_json='{"reason": "EXPIRED_LIMIT_4H"}')

        except Exception as e:
            logger.error(f"Error pada Cron Orphan Order Cleanup: {str(e)}")

    async def _job_failsafe_sync_check(self):
        """
        CRON 3: Failsafe Sync Check (Safety Net jika WebSocket sempat terputus).
        Memeriksa apakah status trade aktif di DB masih cocok dengan posisi di Binance.
        """
        logger.debug("Executing Cron: Failsafe Sync Check with Binance...")
        try:
            async with AsyncSessionLocal() as session:
                trade_repo = TradeRepository(session)
                active_trades = await trade_repo.get_active_trades()

                for trade in active_trades:
                    # Ambil informasi posisi terbuka dari Binance Futures
                    positions = await self.execution_engine.exchange.fetch_positions([trade.symbol])
                    pos = next((p for p in positions if p.get('symbol') == trade.symbol), None)

                    position_qty = abs(float(pos.get('contracts') or pos.get('positionAmt') or 0.0)) if pos else 0.0

                    # Case A: Trade status WAITING_ENTRY tetapi posisi di Binance sudah > 0 (Limit terisi saat WS reconnect)
                    if trade.status == "WAITING_ENTRY" and position_qty > 0:
                        logger.info(f"🔄 [Failsafe Sync] Limit Order #{trade.id} ({trade.symbol}) terdeteksi FILLED di Binance. Syncing DB status -> OPEN.")
                        await trade_repo.update_trade_status(trade.id, "OPEN")
                        await trade_repo.log_event(trade.id, "FAILSAFE_SYNC", f'{{"status": "OPEN", "qty": {position_qty}}}')

                    # Case B: Trade status OPEN/PARTIAL tetapi posisi di Binance sudah 0 (SL/TP tersentuh saat WS reconnect)
                    elif trade.status in ["OPEN", "PARTIAL"] and position_qty == 0:
                        logger.info(f"🔄 [Failsafe Sync] Trade #{trade.id} ({trade.symbol}) terdeteksi CLOSED di Binance. Syncing DB status -> CLOSED.")
                        await trade_repo.update_trade_status(trade.id, "CLOSED", closed_at=datetime.now())
                        await trade_repo.log_event(trade.id, "FAILSAFE_SYNC", '{"status": "CLOSED"}')

        except Exception as e:
            logger.error(f"Error pada Cron Failsafe Sync Check: {str(e)}")

    def stop(self):
        """Menghentikan scheduler."""
        self.scheduler.shutdown()
        logger.info("🛑 Cron Scheduler Stopped.")