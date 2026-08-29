"""Application Bootstrap and Lifespan Manager for Clean Architecture Crypto Bot."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import FastAPI

from config.settings import settings
from src.infrastructure.persistence.connection import init_db
from src.infrastructure.di.container import container
from src.infrastructure.scheduler import SchedulerService
from src.presentation.telegram.bot_controller import TelegramBotController
from src.utils.security import get_password_hash

logger = logging.getLogger("BOOTSTRAP")

# Background task collection
_background_tasks: List[asyncio.Task] = []
_scheduler_service: Optional[Any] = None
_telegram_notifier: Optional[Any] = None


async def initialize_system_defaults() -> None:
    """Ensure default database entities and credentials exist."""
    async with container.session_scope() as session:
        # 1. Ensure default admin user
        user_repo = container.get_user_repo(session)
        default_user = getattr(settings, "DEFAULT_ADMIN_USERNAME", "admin")
        default_pass = getattr(settings, "DEFAULT_ADMIN_PASSWORD", "AdminPassword123!")
        await user_repo.ensure_default_admin(
            default_username=default_user,
            default_password_hash=get_password_hash(default_pass),
        )

        # 2. Warm up active credentials from DB into Exchange Gateway
        acc_repo = container.get_trading_account_repo(session)
        cred_repo = container.get_trading_credential_repo(session)

        active_acc = await acc_repo.get_active_account(exchange_id=1)
        if not active_acc:
            for env_mode in ("TESTNET", "MAINNET"):
                accs = await acc_repo.get_by_environment(env_mode)
                if accs:
                    active_acc = accs[0]
                    break

        if active_acc:
            active_cred = await cred_repo.get_active_credential(active_acc.id)
            if active_cred and active_cred.encrypted_api_key and active_cred.encrypted_secret_key:
                is_testnet = (active_acc.environment.upper() == "TESTNET")
                container.exchange_gateway.reconfigure(
                    api_key=active_cred.encrypted_api_key,
                    secret_key=active_cred.encrypted_secret_key,
                    testnet=is_testnet,
                )
                logger.info(
                    "Reconfigured Exchange Gateway with DB credentials for Account '%s' (%s)",
                    active_acc.name,
                    active_acc.environment,
                )


async def start_background_runners() -> None:
    """Start APScheduler, Binance WebSocket stream, and Telegram bot listener."""
    global _scheduler_service, _telegram_notifier

    # 1. Synchronize Telegram UI Commands
    if container.notification_gateway:
        try:
            await container.notification_gateway.set_my_commands()
            logger.info("Telegram UI Command menu synchronized.")
        except Exception as exc:
            logger.warning("Could not auto-register Telegram UI commands: %s", exc)

    # 2. Start APScheduler (Maintenance & Daily Risk Snapshots)
    try:
        _scheduler_service = SchedulerService()
        _scheduler_service.start()
        logger.info("APScheduler background maintenance jobs started.")
    except Exception as exc:
        logger.warning("Failed to start scheduler: %s", exc)

    # 3. Binance WebSocket Order Fill Listener
    async def on_order_fill_event(order_data: Any) -> None:
        try:
            async with container.session_scope() as fill_session:
                use_case = container.get_handle_order_fill_use_case(fill_session)
                await use_case.execute_from_raw_event(order_data)
        except Exception as exc:
            logger.warning("Error processing WebSocket order fill: %s", exc, exc_info=True)

    try:
        ws_task = container.exchange_gateway.start_order_stream_task(on_fill_coro=on_order_fill_event)
        if ws_task:
            _background_tasks.append(ws_task)
            logger.info("Binance User Data Stream listener running in background.")
    except Exception as exc:
        logger.warning("Could not start Binance WS listener: %s", exc)

    # 4. Telegram Bot Polling Runner
    try:
        tg_task = TelegramBotController.start_polling_task()
        if tg_task:
            _background_tasks.append(tg_task)
            logger.info("Telegram Bot Polling runner active.")
    except Exception as exc:
        logger.warning("Could not start Telegram polling: %s", exc)


async def shutdown_system() -> None:
    """Gracefully terminate background runners, close gateways and dispose DB engine via DI container."""
    logger.info("Initiating graceful system shutdown...")

    # Stop scheduler
    if _scheduler_service:
        try:
            _scheduler_service.stop()
            logger.info("APScheduler stopped.")
        except Exception as exc:
            logger.warning("Error stopping scheduler: %s", exc)

    # Cancel background async tasks (WebSocket & Telegram polling)
    for task in _background_tasks:
        if not task.done():
            task.cancel()

    if _background_tasks:
        try:
            await asyncio.gather(*_background_tasks, return_exceptions=True)
            logger.info("Background listener tasks cancelled.")
        except Exception as exc:
            logger.warning("Error awaiting task cancellations: %s", exc)

    # Release container resources (gateways, event publisher, database engine pool)
    await container.shutdown_resources()
    logger.info("Application shutdown completed cleanly.")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager for FastAPI application."""
    logger.info("🚀 Starting Clean Architecture Crypto Bot Application...")
    try:
        await init_db()
        await container.init_resources()
        await initialize_system_defaults()
        await start_background_runners()
    except Exception as exc:
        logger.error("Error during application startup: %s", exc, exc_info=True)

    yield

    logger.info("🛑 Shutting down Clean Architecture Crypto Bot Application...")
    await shutdown_system()
