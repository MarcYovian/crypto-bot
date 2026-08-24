"""Main Application Entry Point for the Semi-Automated Binance Futures Trading Bot & Web Dashboard API.

Integrates FastAPI REST & WebSocket API, Telegram Polling Bot, Binance Stream Listener,
and APScheduler Background Cron Jobs into a unified Lifespan management architecture.
"""

import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from typing import Optional, List, AsyncIterator

import uvicorn
from fastapi import FastAPI

from config.settings import settings
from src.database.connection import init_db, AsyncSessionLocal, engine
from src.repository.exchange_repository import ExchangeRepository
from src.repository.trading_account_repository import TradingAccountRepository
from src.repository.trading_credential_repository import TradingCredentialRepository
from src.repository.instrument_repository import InstrumentRepository
from src.repository.instrument_leverage_bracket_repository import InstrumentLeverageBracketRepository
from src.repository.watchlist_repository import WatchlistRepository
from src.repository.risk_profile_repository import RiskProfileRepository
from src.repository.strategy_repository import StrategyRepository
from src.repository.signal_provider_repository import SignalProviderRepository
from src.repository.signal_repository import SignalRepository
from src.repository.trade_repository import TradeRepository
from src.repository.trade_risk_repository import TradeRiskRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.order_repository import OrderRepository
from src.repository.execution_repository import ExecutionRepository
from src.repository.trade_event_repository import TradeEventRepository
from src.repository.trade_summary_repository import TradeSummaryRepository
from src.repository.bot_log_repository import BotLogRepository
from src.repository.bot_setting_repository import BotSettingRepository

from src.clients.binance_client import BinanceRestClient, BinanceWebSocketClient
from src.clients.telegram_client import TelegramNotifierClient, TelegramChannelListener

from src.services.precision_filter import PrecisionFilterService
from src.services.signal_parser import SignalParserService
from src.services.risk_calculator import RiskCalculatorService
from src.services.trade_service import TradeService
from src.services.position_manager import PositionManager
from src.services.scheduler_service import SchedulerService
from src.services.telegram_service import TelegramService
from src.services.instrument_service import InstrumentService
from src.api.app import create_app

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("ccxt").setLevel(logging.WARNING)
logger = logging.getLogger("MAIN_APP")


class ApplicationContainer:
    """Dependency Injection Container and Runtime Lifecycle Manager."""

    def __init__(self) -> None:
        self.running = False
        self.session_maker = AsyncSessionLocal

        # External Clients
        self.binance_client: Optional[BinanceRestClient] = None
        self.binance_ws: Optional[BinanceWebSocketClient] = None
        self.telegram_client: Optional[TelegramNotifierClient] = None
        self.telegram_listener: Optional[TelegramChannelListener] = None

        # Business Services
        self.precision_service: Optional[PrecisionFilterService] = None
        self.signal_parser: Optional[SignalParserService] = None
        self.risk_calculator: Optional[RiskCalculatorService] = None
        self.trade_service: Optional[TradeService] = None
        self.position_manager: Optional[PositionManager] = None
        self.scheduler: Optional[SchedulerService] = None
        self.telegram_service: Optional[TelegramService] = None

        # Async Tasks
        self.tasks: List[asyncio.Task] = []

    async def initialize(self) -> None:
        """Initialize database credentials, third-party clients, repositories, and domain services."""
        # 1. Load active API credentials and environment strictly from Database
        active_api_key: Optional[str] = None
        active_api_secret: Optional[str] = None
        active_testnet: bool = True

        async with self.session_maker() as init_session:
            acc_repo = TradingAccountRepository(init_session)
            cred_repo = TradingCredentialRepository(init_session)

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
                    active_api_key = active_cred.encrypted_api_key
                    active_api_secret = active_cred.encrypted_secret_key
                    active_testnet = (active_acc.environment.upper() == "TESTNET")
                    logger.info(
                        f"Loaded active Binance credentials from Database: Account '{active_acc.name}' "
                        f"({active_acc.environment}), Key: {active_api_key[:4]}****{active_api_key[-4:]}"
                    )
            else:
                logger.info("No active Binance credentials in Database. Use /setup_account in Telegram or Web UI.")

        # 2. External Clients
        self.binance_client = BinanceRestClient(
            api_key=active_api_key,
            api_secret=active_api_secret,
            testnet=active_testnet,
        )
        self.binance_ws = BinanceWebSocketClient(
            api_key=active_api_key,
            api_secret=active_api_secret,
            testnet=active_testnet,
        )
        self.telegram_client = TelegramNotifierClient(
            bot_token=settings.TELEGRAM_BOT_TOKEN,
            default_chat_id=settings.TELEGRAM_CHAT_ID,
        )
        if getattr(settings, "TELEGRAM_APP_ID", None) and getattr(settings, "TELEGRAM_APP_HASH", None):
            self.telegram_listener = TelegramChannelListener(
                session_name="crypto_bot_listener",
                api_id=int(settings.TELEGRAM_APP_ID),
                api_hash=settings.TELEGRAM_APP_HASH,
            )

        # 3. Domain Services
        self.precision_service = PrecisionFilterService()
        self.signal_parser = SignalParserService()
        self.risk_calculator = RiskCalculatorService()

        logger.info("Application Container dependencies initialized successfully.")

    async def start_background_runners(self) -> None:
        """Start background runners: APScheduler, WebSocket Stream, and Telegram Polling."""
        self.running = True
        logger.info("Starting background services (Scheduler, Telegram, Binance Stream)...")

        async with self.session_maker() as session:
            # Repositories for scoped services
            inst_repo = InstrumentRepository(session)
            watch_repo = WatchlistRepository(session)
            trade_repo = TradeRepository(session)
            trade_risk_repo = TradeRiskRepository(session)
            daily_risk_repo = DailyRiskRepository(session)
            order_repo = OrderRepository(session)
            exec_repo = ExecutionRepository(session)
            trade_event_repo = TradeEventRepository(session)
            trade_sum_repo = TradeSummaryRepository(session)
            bot_log_repo = BotLogRepository(session)
            bot_setting_repo = BotSettingRepository(session)
            signal_repo = SignalRepository(session)
            signal_prov_repo = SignalProviderRepository(session)
            risk_prof_repo = RiskProfileRepository(session)
            acc_repo = TradingAccountRepository(session)
            inst_bracket_repo = InstrumentLeverageBracketRepository(session)
            ex_repo = ExchangeRepository(session)
            cred_repo = TradingCredentialRepository(session)

            self.trade_service = TradeService(
                instrument_repo=inst_repo,
                watchlist_repo=watch_repo,
                trade_repo=trade_repo,
                trade_risk_repo=trade_risk_repo,
                daily_risk_repo=daily_risk_repo,
                order_repo=order_repo,
                trade_event_repo=trade_event_repo,
                bracket_repo=inst_bracket_repo,
                risk_calculator=self.risk_calculator,
                binance_client=self.binance_client,
                telegram_client=self.telegram_client,
            )

            self.position_manager = PositionManager(
                trade_repo=trade_repo,
                order_repo=order_repo,
                execution_repo=exec_repo,
                trade_event_repo=trade_event_repo,
                trade_summary_repo=trade_sum_repo,
                daily_risk_repo=daily_risk_repo,
                binance_client=self.binance_client,
                telegram_client=self.telegram_client,
            )

            inst_service = InstrumentService(
                instrument_repo=inst_repo,
                exchange_repo=ex_repo,
                watchlist_repo=watch_repo,
                bracket_repo=inst_bracket_repo,
                binance_client=self.binance_client,
            )

            self.scheduler = SchedulerService(
                daily_risk_repo=daily_risk_repo,
                trading_account_repo=acc_repo,
                risk_profile_repo=risk_prof_repo,
                trade_repo=trade_repo,
                order_repo=order_repo,
                instrument_repo=inst_repo,
                trade_summary_repo=trade_sum_repo,
                trade_event_repo=trade_event_repo,
                bot_log_repo=bot_log_repo,
                bot_setting_repo=bot_setting_repo,
                position_manager=self.position_manager,
                instrument_service=inst_service,
                binance_client=self.binance_client,
                telegram_client=self.telegram_client,
            )

            self.telegram_service = TelegramService(
                signal_parser=self.signal_parser,
                risk_calculator=self.risk_calculator,
                trade_service=self.trade_service,
                signal_repo=signal_repo,
                trade_repo=trade_repo,
                order_repo=order_repo,
                daily_risk_repo=daily_risk_repo,
                trade_summary_repo=trade_sum_repo,
                watchlist_repo=watch_repo,
                instrument_repo=inst_repo,
                risk_profile_repo=risk_prof_repo,
                bot_log_repo=bot_log_repo,
                bot_setting_repo=bot_setting_repo,
                signal_provider_repo=signal_prov_repo,
                instrument_service=inst_service,
                exchange_repo=ex_repo,
                trading_account_repo=acc_repo,
                trading_credential_repo=cred_repo,
                position_manager=self.position_manager,
                binance_client=self.binance_client,
                telegram_client=self.telegram_client,
            )

            # 1. Register Telegram UI Command Menu
            if self.telegram_client and settings.TELEGRAM_BOT_TOKEN:
                try:
                    await self.telegram_client.set_my_commands()
                    logger.info("Telegram UI Command menu synchronized successfully.")
                except Exception as e:
                    logger.warning(f"Could not auto-register Telegram commands: {e}")

            # 2. Start APScheduler Background Jobs
            if self.scheduler:
                self.scheduler.start()
                logger.info("APScheduler background jobs active (7 maintenance jobs).")

            # 3. Telegram Polling dispatcher
            async def on_tg_message(msg: dict):
                text = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id", 1)
                message_id = msg.get("message_id")
                if not text:
                    return

                async with self.session_maker() as sig_session:
                    inst_s = InstrumentService(
                        instrument_repo=InstrumentRepository(sig_session),
                        exchange_repo=ExchangeRepository(sig_session),
                        watchlist_repo=WatchlistRepository(sig_session),
                        bracket_repo=InstrumentLeverageBracketRepository(sig_session),
                        binance_client=self.binance_client,
                    )
                    t_serv = TelegramService(
                        signal_parser=self.signal_parser,
                        risk_calculator=self.risk_calculator,
                        trade_service=TradeService(
                            instrument_repo=InstrumentRepository(sig_session),
                            watchlist_repo=WatchlistRepository(sig_session),
                            trade_repo=TradeRepository(sig_session),
                            trade_risk_repo=TradeRiskRepository(sig_session),
                            daily_risk_repo=DailyRiskRepository(sig_session),
                            order_repo=OrderRepository(sig_session),
                            trade_event_repo=TradeEventRepository(sig_session),
                            bracket_repo=InstrumentLeverageBracketRepository(sig_session),
                            risk_calculator=self.risk_calculator,
                            binance_client=self.binance_client,
                            telegram_client=self.telegram_client,
                        ),
                        signal_repo=SignalRepository(sig_session),
                        trade_repo=TradeRepository(sig_session),
                        order_repo=OrderRepository(sig_session),
                        daily_risk_repo=DailyRiskRepository(sig_session),
                        trade_summary_repo=TradeSummaryRepository(sig_session),
                        watchlist_repo=WatchlistRepository(sig_session),
                        instrument_repo=InstrumentRepository(sig_session),
                        risk_profile_repo=RiskProfileRepository(sig_session),
                        bot_log_repo=BotLogRepository(sig_session),
                        bot_setting_repo=BotSettingRepository(sig_session),
                        signal_provider_repo=SignalProviderRepository(sig_session),
                        instrument_service=inst_s,
                        exchange_repo=ExchangeRepository(sig_session),
                        trading_account_repo=TradingAccountRepository(sig_session),
                        trading_credential_repo=TradingCredentialRepository(sig_session),
                        position_manager=self.position_manager,
                        binance_client=self.binance_client,
                        telegram_client=self.telegram_client,
                    )
                    reply = await t_serv.handle_user_message(raw_text=text, chat_id=chat_id, message_id=message_id)
                    if text.strip().lower() in ("/setup_account", "/account_setup", "/set_credentials"):
                        return
                    if reply and isinstance(reply, str) and self.telegram_client:
                        try:
                            await self.telegram_client.send_message(chat_id=chat_id, text=reply)
                        except Exception as e:
                            logger.error(f"Error sending reply message: {e}")

            async def on_tg_callback_query(cq: dict):
                callback_data = cq.get("data", "")
                cq_id = cq.get("id")
                msg = cq.get("message", {})
                chat_id = msg.get("chat", {}).get("id", 1)
                message_id = msg.get("message_id")

                if self.telegram_client and cq_id:
                    try:
                        await self.telegram_client.answer_callback_query(callback_query_id=cq_id)
                    except Exception:
                        pass

                async with self.session_maker() as cb_session:
                    inst_s = InstrumentService(
                        instrument_repo=InstrumentRepository(cb_session),
                        exchange_repo=ExchangeRepository(cb_session),
                        watchlist_repo=WatchlistRepository(cb_session),
                        bracket_repo=InstrumentLeverageBracketRepository(cb_session),
                        binance_client=self.binance_client,
                    )
                    t_serv = TelegramService(
                        signal_parser=self.signal_parser,
                        risk_calculator=self.risk_calculator,
                        trade_service=TradeService(
                            instrument_repo=InstrumentRepository(cb_session),
                            watchlist_repo=WatchlistRepository(cb_session),
                            trade_repo=TradeRepository(cb_session),
                            trade_risk_repo=TradeRiskRepository(cb_session),
                            daily_risk_repo=DailyRiskRepository(cb_session),
                            order_repo=OrderRepository(cb_session),
                            trade_event_repo=TradeEventRepository(cb_session),
                            bracket_repo=InstrumentLeverageBracketRepository(cb_session),
                            risk_calculator=self.risk_calculator,
                            binance_client=self.binance_client,
                            telegram_client=self.telegram_client,
                        ),
                        signal_repo=SignalRepository(cb_session),
                        trade_repo=TradeRepository(cb_session),
                        order_repo=OrderRepository(cb_session),
                        daily_risk_repo=DailyRiskRepository(cb_session),
                        trade_summary_repo=TradeSummaryRepository(cb_session),
                        watchlist_repo=WatchlistRepository(cb_session),
                        instrument_repo=InstrumentRepository(cb_session),
                        risk_profile_repo=RiskProfileRepository(cb_session),
                        bot_log_repo=BotLogRepository(cb_session),
                        bot_setting_repo=BotSettingRepository(cb_session),
                        signal_provider_repo=SignalProviderRepository(cb_session),
                        instrument_service=inst_s,
                        exchange_repo=ExchangeRepository(cb_session),
                        trading_account_repo=TradingAccountRepository(cb_session),
                        trading_credential_repo=TradingCredentialRepository(cb_session),
                        position_manager=self.position_manager,
                        binance_client=self.binance_client,
                        telegram_client=self.telegram_client,
                    )
                    await t_serv.handle_callback_query(
                        callback_data=callback_data,
                        message_id=message_id,
                        chat_id=chat_id,
                    )

            if self.telegram_client and settings.TELEGRAM_BOT_TOKEN:
                tg_task = asyncio.create_task(
                    self.telegram_client.start_polling(
                        on_message_coro=on_tg_message,
                        on_callback_query_coro=on_tg_callback_query,
                    )
                )
                self.tasks.append(tg_task)
                logger.info("Telegram interactive bot polling task active.")

            logger.info("🚀 Semi-Automated Crypto Bot services fully initialized.")

    async def shutdown(self) -> None:
        """Gracefully terminate background runners, close client sockets and database engine."""
        logger.info("🛑 Initiating graceful shutdown...")
        self.running = False

        # Stop Scheduler
        if self.scheduler:
            try:
                self.scheduler.stop()
                logger.info("APScheduler stopped.")
            except Exception as e:
                logger.warning(f"Error stopping scheduler: {e}")

        # Cancel background tasks
        for t in self.tasks:
            if not t.done():
                t.cancel()

        # Close Binance WebSocket & REST
        if self.binance_ws:
            try:
                await self.binance_ws.close()
            except Exception:
                pass
        if self.binance_client:
            try:
                await self.binance_client.close()
            except Exception:
                pass

        # Close Telegram Client & Polling
        if self.telegram_client:
            try:
                await self.telegram_client.stop_polling()
                await self.telegram_client.close()
            except Exception:
                pass

        # Close Telegram Listener
        if self.telegram_listener:
            try:
                await self.telegram_listener.disconnect()
            except Exception:
                pass

        # Dispose DB connection pool
        await engine.dispose()
        logger.info("Database engine pool disposed. Bot successfully stopped.")


container = ApplicationContainer()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Unified FastAPI Lifespan Context Manager.

    Coordinates database schema migration, container initialization,
    background runner orchestration, and graceful shutdown.
    """
    logger.info("Starting up FastAPI application lifespan context...")
    try:
        await init_db()
        await container.initialize()
        await container.start_background_runners()
    except Exception as e:
        logger.error(f"Error during application startup initialization: {e}")

    yield

    logger.info("Shutting down FastAPI application lifespan context...")
    await container.shutdown()


# Instantiate FastAPI app with lifespan manager
app = create_app(lifespan=lifespan)


def handle_exit_signal(sig, frame):
    """Signal handler for SIGINT and SIGTERM."""
    logger.info(f"Received OS interrupt signal ({sig}). Requesting shutdown...")
    asyncio.create_task(container.shutdown())


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level=settings.LOG_LEVEL.lower(),
    )
