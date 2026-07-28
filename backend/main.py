"""Entry point for the semi-automated Binance Futures trading bot."""

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

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("MAIN")


async def main():
    """Initialise all modules and run the bot loop.

    Startup sequence:
    1. Create database tables (if missing).
    2. Create the Binance execution engine.
    3. Start the cron scheduler.
    4. Start the WebSocket listener (background task).
    5. Start the Telegram bot (polling).
    6. Idle (``asyncio.sleep`` loop) until ``KeyboardInterrupt``.

    On shutdown all modules receive a graceful stop signal.
    """
    logger.info("Starting Semi-Automated Binance Futures Bot V2")

    await init_db()

    execution_engine = BinanceExecutionEngine()

    async with AsyncSessionLocal() as session:
        trade_repo = TradeRepository(session)
        position_manager = PositionManager(trade_repo, execution_engine)

        cron_scheduler = CronSchedulerService(execution_engine)
        cron_scheduler.start()
        await cron_scheduler.run_initial_daily_risk_check()

        ws_listener = BinanceStreamListener(trade_repo, position_manager)
        ws_task = asyncio.create_task(ws_listener.start())

        telegram_service = TelegramService(
            execution_engine=execution_engine,
            token=settings.TELEGRAM_BOT_TOKEN,
            allowed_chat_id=settings.TELEGRAM_CHAT_ID
        )

        logger.info("All Bot Modules Active & Running! Listening for Signals...")

        try:
            await telegram_service.app.initialize()
            await telegram_service.app.start()
            await telegram_service.app.updater.start_polling()

            while True:
                await asyncio.sleep(1)

        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutdown signal received...")
        finally:
            logger.info("Cleaning up and stopping processes...")
            cron_scheduler.stop()
            await ws_listener.stop()
            ws_task.cancel()
            await execution_engine.close_connection()
            await telegram_service.app.updater.stop()
            await telegram_service.app.stop()
            logger.info("Bot gracefully stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Fatal startup error: {e}", exc_info=True)
