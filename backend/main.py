# backend/main.py
import asyncio
import logging
import sys
from pytz import timezone

from config.settings import settings
from src.database.connection import init_db, AsyncSessionLocal
from src.repository.trade_repository import TradeRepository
from src.repository.signal_repository import SignalRepository
from src.services.execution_engine import BinanceExecutionEngine
from src.services.position_manager import PositionManager
from src.services.websocket_listener import BinanceStreamListener
from src.services.telegram_service import TelegramService
from src.services.scheduler_service import CronSchedulerService

# Setup Centralized Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("MAIN")


async def main():
    logger.info("==================================================")
    logger.info("🚀 Starting Semi-Automated Binance Futures Bot V2")
    logger.info("==================================================")

    # 1. Inisialisasi Database SQLite & Tabel
    logger.info("Initializing Database...")
    await init_db()

    # 2. Inisialisasi Execution Engine
    execution_engine = BinanceExecutionEngine()

    async with AsyncSessionLocal() as session:
        trade_repo = TradeRepository(session)
        position_manager = PositionManager(trade_repo, execution_engine)
        
        # 3. Inisialisasi & Jalankan Cron Scheduler
        cron_scheduler = CronSchedulerService(execution_engine)
        cron_scheduler.start()
        # Jalankan initial check untuk memastikan Snapshot Risk hari ini sudah dibuat
        await cron_scheduler.run_initial_daily_risk_check()

        # 4. Inisialisasi & Jalankan Binance WebSocket Listener (Background Task)
        ws_listener = BinanceStreamListener(trade_repo, position_manager)
        ws_task = asyncio.create_task(ws_listener.start())

        # 5. Inisialisasi Telegram Bot Listener
        telegram_service = TelegramService(
            execution_engine=execution_engine,
            token=settings.TELEGRAM_BOT_TOKEN,
            allowed_chat_id=settings.TELEGRAM_CHAT_ID
        )

        logger.info("🔥 All Bot Modules Active & Running! Listening for Signals...")

        try:
            # Jalankan Telegram Listener (Async Polling)
            await telegram_service.app.initialize()
            await telegram_service.app.start()
            await telegram_service.app.updater.start_polling()

            # Menjaga Loop Tetap Berjalan
            while True:
                await asyncio.sleep(1)

        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutdown Signal Received...")
        finally:
            # Graceful Shutdown Sequence
            logger.info("Cleaning up and stopping processes...")
            cron_scheduler.stop()
            await ws_listener.stop()
            ws_task.cancel()
            await execution_engine.close_connection()
            await telegram_service.app.updater.stop()
            await telegram_service.app.stop()
            logger.info("👋 Bot Gracefully Stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Fatal Startup Error: {e}", exc_info=True)
