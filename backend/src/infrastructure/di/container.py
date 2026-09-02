"""Native Dependency Injection Container (Option A) for managing application lifecycle, use cases, and services."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional
from unittest.mock import MagicMock

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from config.settings import settings
from src.infrastructure.persistence.connection import engine as default_engine, AsyncSessionLocal
from src.domain.ports.gateways import IExchangeGateway, INotificationGateway
from src.domain.ports.event_publisher import IDomainEventPublisher
from src.infrastructure.gateways.binance import (
    BinanceConnector,
    BinanceParser,
    BinanceValidator,
    BinanceExchangeAdapter,
)
from src.infrastructure.gateways.telegram import (
    TelegramConnector,
    TelegramFormatter,
    TelegramNotificationAdapter,
)
from src.infrastructure.events import InMemoryDomainEventPublisher

from src.domain.events.trade_events import (
    TradeOpenedEvent,
    TradeWaitingEntryEvent,
    TradePartiallyClosedEvent,
    StopLossMovedEvent,
    TradeClosedEvent,
)
from src.application.event_handlers import TradeNotificationEventHandler

from src.infrastructure.persistence.repositories import (
    TradeRepository,
    OrderRepository,
    InstrumentRepository,
    InstrumentLeverageBracketRepository,
    WatchlistRepository,
    DailyRiskRepository,
    RiskProfileRepository,
    SignalRepository,
    SignalProviderRepository,
    StrategyRepository,
    TradingAccountRepository,
    TradingCredentialRepository,
    ExecutionRepository,
    TradeEventRepository,
    TradeSummaryRepository,
    BotSettingRepository,
    BotLogRepository,
    UserRepository,
    ExchangeRepository,
    TradeRiskRepository,
)

from src.application.use_cases.trades import (
    ExecuteSignalUseCase,
    HandleOrderFillUseCase,
    CloseTradeUseCase,
    UpdateStopLossUseCase,
    SyncPositionsUseCase,
    GetActiveTradesUseCase,
    GetTradeHistoryUseCase,
    GetTradeDetailUseCase,
    PlaceBracketOrdersUseCase,
)

from src.application.use_cases.risk import (
    SimulateRiskUseCase,
    CheckDailyRiskUseCase,
)
from src.application.use_cases.signals import (
    ParseSignalUseCase,
    ApproveSignalUseCase,
    RejectSignalUseCase,
    GetSignalsFeedUseCase,
    ManualExecuteSignalUseCase,
)
from src.application.use_cases.telegram import (
    HandleTelegramCommandUseCase,
)
from src.application.use_cases.bot import (
    GetBotStatusUseCase,
    PauseBotUseCase,
    ResumeBotUseCase,
    PanicCloseUseCase,
    GetSettingsUseCase,
    UpdateSettingsUseCase,
    SaveCredentialsUseCase,
)
from src.application.use_cases.analytics import (
    GetDashboardSummaryUseCase,
    GetEquityCurveUseCase,
)
from src.application.use_cases.auth import (
    LoginUseCase,
    RefreshTokenUseCase,
)
from src.application.use_cases.instruments import (
    ListInstrumentsUseCase,
    SyncInstrumentsUseCase,
)
from src.application.use_cases.watchlist import (
    GetWatchlistUseCase,
    ToggleWatchlistUseCase,
)
from src.application.use_cases.providers import (
    ListProvidersUseCase,
    CreateProviderUseCase,
    GetProviderPerformanceUseCase,
)
from src.application.use_cases.strategies import (
    ListStrategiesUseCase,
    UpdateStrategyUseCase,
)
from src.application.use_cases.reports import (
    ExportTradesCsvUseCase,
)
from src.application.use_cases.logs import (
    GetLogsUseCase,
)



logger = logging.getLogger(__name__)


class ApplicationContainer:
    """Native DI Container managing Singletons, Scoped Database Sessions, Gateway Adapters, and Use Cases."""

    def __init__(
        self,
        db_engine: Optional[AsyncEngine] = None,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        testnet: bool = True,
    ) -> None:
        # 1. Database Infrastructure
        self._engine: AsyncEngine = db_engine or default_engine
        self._session_factory: async_sessionmaker[AsyncSession] = (
            session_factory or AsyncSessionLocal
        )
        self.session_maker = self._session_factory
        self.running: bool = False
        self.scheduler: Optional[Any] = None

        # 2. Event Publisher (Singleton)
        self.event_publisher: InMemoryDomainEventPublisher = InMemoryDomainEventPublisher()

        # 3. Binance Gateway (Singleton Adapter)
        self.binance_connector: BinanceConnector = BinanceConnector(
            api_key=settings.BINANCE_API_KEY if hasattr(settings, "BINANCE_API_KEY") else None,
            secret_key=settings.BINANCE_API_SECRET if hasattr(settings, "BINANCE_API_SECRET") else None,
            testnet=getattr(settings, "BINANCE_TESTNET", testnet),
        )
        self.binance_parser: BinanceParser = BinanceParser()
        self.binance_validator: BinanceValidator = BinanceValidator()
        self.exchange_gateway: BinanceExchangeAdapter = BinanceExchangeAdapter(
            connector=self.binance_connector,
            parser=self.binance_parser,
            validator=self.binance_validator,
        )

        # 4. Telegram Gateway (Singleton Adapter)
        self.telegram_connector: TelegramConnector = TelegramConnector(
            bot_token=getattr(settings, "TELEGRAM_BOT_TOKEN", None),
            default_chat_id=getattr(settings, "TELEGRAM_CHAT_ID", None),
        )
        self.telegram_formatter: TelegramFormatter = TelegramFormatter()
        self.notification_gateway: TelegramNotificationAdapter = TelegramNotificationAdapter(
            connector=self.telegram_connector,
            formatter=self.telegram_formatter,
        )

        # 5. Event Handlers
        self.trade_notification_handler = TradeNotificationEventHandler(
            notification_gateway=self.notification_gateway
        )

        self._is_initialized = False
        self._lock = asyncio.Lock()

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory

    @asynccontextmanager
    async def session_scope(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a transactional asynchronous database session scope."""
        session: AsyncSession = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """FastAPI Dependency yield provider for AsyncSession."""
        async with self.session_scope() as session:
            yield session

    # -------------------------------------------------------------------------
    # Repository Factories (Scoped per Session)
    # -------------------------------------------------------------------------
    @staticmethod
    def get_trade_repo(session: AsyncSession) -> TradeRepository:
        return TradeRepository(session)

    @staticmethod
    def get_order_repo(session: AsyncSession) -> OrderRepository:
        return OrderRepository(session)

    @staticmethod
    def get_instrument_repo(session: AsyncSession) -> InstrumentRepository:
        return InstrumentRepository(session)

    @staticmethod
    def get_bracket_repo(session: AsyncSession) -> InstrumentLeverageBracketRepository:
        return InstrumentLeverageBracketRepository(session)

    @staticmethod
    def get_watchlist_repo(session: AsyncSession) -> WatchlistRepository:
        return WatchlistRepository(session)

    @staticmethod
    def get_daily_risk_repo(session: AsyncSession) -> DailyRiskRepository:
        return DailyRiskRepository(session)

    @staticmethod
    def get_risk_profile_repo(session: AsyncSession) -> RiskProfileRepository:
        return RiskProfileRepository(session)

    @staticmethod
    def get_signal_repo(session: AsyncSession) -> SignalRepository:
        return SignalRepository(session)

    @staticmethod
    def get_signal_provider_repo(session: AsyncSession) -> SignalProviderRepository:
        return SignalProviderRepository(session)

    @staticmethod
    def get_strategy_repo(session: AsyncSession) -> StrategyRepository:
        return StrategyRepository(session)

    @staticmethod
    def get_trading_account_repo(session: AsyncSession) -> TradingAccountRepository:
        return TradingAccountRepository(session)

    @staticmethod
    def get_trading_credential_repo(session: AsyncSession) -> TradingCredentialRepository:
        return TradingCredentialRepository(session)

    @staticmethod
    def get_execution_repo(session: AsyncSession) -> ExecutionRepository:
        return ExecutionRepository(session)

    @staticmethod
    def get_trade_event_repo(session: AsyncSession) -> TradeEventRepository:
        return TradeEventRepository(session)

    @staticmethod
    def get_trade_summary_repo(session: AsyncSession) -> TradeSummaryRepository:
        return TradeSummaryRepository(session)

    @staticmethod
    def get_trade_risk_repo(session: AsyncSession) -> TradeRiskRepository:
        return TradeRiskRepository(session)

    @staticmethod
    def get_bot_setting_repo(session: AsyncSession) -> BotSettingRepository:
        return BotSettingRepository(session)

    @staticmethod
    def get_bot_log_repo(session: AsyncSession) -> BotLogRepository:
        return BotLogRepository(session)

    @staticmethod
    def get_user_repo(session: AsyncSession) -> UserRepository:
        return UserRepository(session)

    @staticmethod
    def get_exchange_repo(session: AsyncSession) -> ExchangeRepository:
        return ExchangeRepository(session)


    # -------------------------------------------------------------------------
    # Use Case Factories (Scoped per Session)
    # -------------------------------------------------------------------------
    def get_place_bracket_orders_use_case(self, session: AsyncSession) -> PlaceBracketOrdersUseCase:
        return PlaceBracketOrdersUseCase(
            order_repo=self.get_order_repo(session),
            exchange_gateway=self.exchange_gateway,
            trade_repo=self.get_trade_repo(session),
        )

    def get_execute_signal_use_case(self, session: AsyncSession) -> ExecuteSignalUseCase:
        return ExecuteSignalUseCase(
            instrument_repo=self.get_instrument_repo(session),
            watchlist_repo=self.get_watchlist_repo(session),
            trade_repo=self.get_trade_repo(session),
            trade_risk_repo=self.get_trade_risk_repo(session),
            daily_risk_repo=self.get_daily_risk_repo(session),
            order_repo=self.get_order_repo(session),
            trade_event_repo=self.get_trade_event_repo(session),
            risk_profile_repo=self.get_risk_profile_repo(session),
            bracket_repo=self.get_bracket_repo(session),
            strategy_repo=self.get_strategy_repo(session),
            exchange_gateway=self.exchange_gateway,
            event_publisher=self.event_publisher,
            place_bracket_orders_use_case=self.get_place_bracket_orders_use_case(session),
        )

    def get_handle_order_fill_use_case(self, session: AsyncSession) -> HandleOrderFillUseCase:
        return HandleOrderFillUseCase(
            trade_repo=self.get_trade_repo(session),
            order_repo=self.get_order_repo(session),
            execution_repo=self.get_execution_repo(session),
            trade_event_repo=self.get_trade_event_repo(session),
            trade_risk_repo=self.get_trade_risk_repo(session),
            trade_summary_repo=self.get_trade_summary_repo(session),
            daily_risk_repo=self.get_daily_risk_repo(session),
            instrument_repo=self.get_instrument_repo(session),
            exchange_gateway=self.exchange_gateway,
            event_publisher=self.event_publisher,
            place_bracket_orders_use_case=self.get_place_bracket_orders_use_case(session),
        )


    def get_close_trade_use_case(self, session: AsyncSession) -> CloseTradeUseCase:
        return CloseTradeUseCase(
            trade_repo=self.get_trade_repo(session),
            order_repo=self.get_order_repo(session),
            trade_event_repo=self.get_trade_event_repo(session),
            trade_summary_repo=self.get_trade_summary_repo(session),
            exchange_gateway=self.exchange_gateway,
            event_publisher=self.event_publisher,
        )

    def get_update_stop_loss_use_case(self, session: AsyncSession) -> UpdateStopLossUseCase:
        return UpdateStopLossUseCase(
            trade_repo=self.get_trade_repo(session),
            order_repo=self.get_order_repo(session),
            trade_event_repo=self.get_trade_event_repo(session),
            exchange_gateway=self.exchange_gateway,
            event_publisher=self.event_publisher,
        )

    def get_sync_positions_use_case(self, session: AsyncSession) -> SyncPositionsUseCase:
        return SyncPositionsUseCase(
            trade_repo=self.get_trade_repo(session),
            instrument_repo=self.get_instrument_repo(session),
            exchange_gateway=self.exchange_gateway,
            order_repo=self.get_order_repo(session),
            execution_repo=self.get_execution_repo(session),
            trade_summary_repo=self.get_trade_summary_repo(session),
            event_publisher=self.event_publisher,
        )

    def get_simulate_risk_use_case(self, session: AsyncSession) -> SimulateRiskUseCase:
        return SimulateRiskUseCase(
            instrument_repo=self.get_instrument_repo(session),
            risk_profile_repo=self.get_risk_profile_repo(session),
            daily_risk_repo=self.get_daily_risk_repo(session),
            bracket_repo=self.get_bracket_repo(session),
            exchange_gateway=self.exchange_gateway,
        )

    def get_check_daily_risk_use_case(self, session: AsyncSession) -> CheckDailyRiskUseCase:
        return CheckDailyRiskUseCase(
            daily_risk_repo=self.get_daily_risk_repo(session),
            risk_profile_repo=self.get_risk_profile_repo(session),
            trade_repo=self.get_trade_repo(session),
        )

    def get_parse_signal_use_case(self, session: AsyncSession) -> ParseSignalUseCase:
        return ParseSignalUseCase(
            signal_repo=self.get_signal_repo(session),
            instrument_repo=self.get_instrument_repo(session),
            event_publisher=self.event_publisher,
        )

    def get_approve_signal_use_case(self, session: AsyncSession) -> ApproveSignalUseCase:
        return ApproveSignalUseCase(
            signal_repo=self.get_signal_repo(session),
            execute_signal_use_case=self.get_execute_signal_use_case(session),
            event_publisher=self.event_publisher,
        )

    def get_reject_signal_use_case(self, session: AsyncSession) -> RejectSignalUseCase:
        return RejectSignalUseCase(
            signal_repo=self.get_signal_repo(session),
            event_publisher=self.event_publisher,
        )

    def get_get_active_trades_use_case(self, session: AsyncSession) -> GetActiveTradesUseCase:
        return GetActiveTradesUseCase(trade_repo=self.get_trade_repo(session))

    def get_get_trade_history_use_case(self, session: AsyncSession) -> GetTradeHistoryUseCase:
        return GetTradeHistoryUseCase(trade_repo=self.get_trade_repo(session))

    def get_get_trade_detail_use_case(self, session: AsyncSession) -> GetTradeDetailUseCase:
        return GetTradeDetailUseCase(trade_repo=self.get_trade_repo(session))

    def get_get_signals_feed_use_case(self, session: AsyncSession) -> GetSignalsFeedUseCase:
        return GetSignalsFeedUseCase(signal_repo=self.get_signal_repo(session))

    def get_manual_execute_signal_use_case(self, session: AsyncSession) -> ManualExecuteSignalUseCase:
        return ManualExecuteSignalUseCase(
            execute_signal_use_case=self.get_execute_signal_use_case(session)
        )

    def get_telegram_command_use_case(self, session: AsyncSession) -> HandleTelegramCommandUseCase:
        return HandleTelegramCommandUseCase(
            trade_repo=self.get_trade_repo(session),
            order_repo=self.get_order_repo(session),
            watchlist_repo=self.get_watchlist_repo(session),
            bot_log_repo=self.get_bot_log_repo(session),
            daily_risk_repo=self.get_daily_risk_repo(session),
            trade_summary_repo=self.get_trade_summary_repo(session),
            bot_setting_repo=self.get_bot_setting_repo(session),
            trading_account_repo=self.get_trading_account_repo(session),
            trading_credential_repo=self.get_trading_credential_repo(session),
            instrument_repo=self.get_instrument_repo(session),
            risk_profile_repo=self.get_risk_profile_repo(session),
            close_trade_use_case=self.get_close_trade_use_case(session),
            exchange_gateway=self.exchange_gateway,
            notification_gateway=self.notification_gateway,
        )

    def get_handle_command_use_case(self, session: AsyncSession) -> HandleTelegramCommandUseCase:
        """Alias for get_telegram_command_use_case."""
        return self.get_telegram_command_use_case(session)

    # Bot and Settings Use Cases
    def get_get_bot_status_use_case(self, session: AsyncSession) -> GetBotStatusUseCase:
        return GetBotStatusUseCase(bot_setting_repo=self.get_bot_setting_repo(session))

    def get_pause_bot_use_case(self, session: AsyncSession) -> PauseBotUseCase:
        return PauseBotUseCase(bot_setting_repo=self.get_bot_setting_repo(session))

    def get_resume_bot_use_case(self, session: AsyncSession) -> ResumeBotUseCase:
        return ResumeBotUseCase(bot_setting_repo=self.get_bot_setting_repo(session))

    def get_panic_close_use_case(self, session: AsyncSession) -> PanicCloseUseCase:
        return PanicCloseUseCase(
            bot_setting_repo=self.get_bot_setting_repo(session),
            trade_repo=self.get_trade_repo(session),
            order_repo=self.get_order_repo(session),
        )

    def get_get_settings_use_case(self, session: AsyncSession) -> GetSettingsUseCase:
        return GetSettingsUseCase(
            bot_setting_repo=self.get_bot_setting_repo(session),
            risk_profile_repo=self.get_risk_profile_repo(session),
        )

    def get_update_settings_use_case(self, session: AsyncSession) -> UpdateSettingsUseCase:
        return UpdateSettingsUseCase(
            bot_setting_repo=self.get_bot_setting_repo(session),
            risk_profile_repo=self.get_risk_profile_repo(session),
        )

    def get_save_credentials_use_case(self, session: AsyncSession) -> SaveCredentialsUseCase:
        return SaveCredentialsUseCase(
            credential_repo=self.get_trading_credential_repo(session),
            account_repo=self.get_trading_account_repo(session),
            exchange_repo=self.get_exchange_repo(session),
            exchange_gateway=self.exchange_gateway,
        )

    # Analytics Use Cases
    def get_get_dashboard_summary_use_case(self, session: AsyncSession) -> GetDashboardSummaryUseCase:
        return GetDashboardSummaryUseCase(
            daily_risk_repo=self.get_daily_risk_repo(session),
            trade_summary_repo=self.get_trade_summary_repo(session),
            trade_repo=self.get_trade_repo(session),
        )

    def get_get_equity_curve_use_case(self, session: AsyncSession) -> GetEquityCurveUseCase:
        return GetEquityCurveUseCase(
            daily_risk_repo=self.get_daily_risk_repo(session),
            trade_summary_repo=self.get_trade_summary_repo(session),
        )

    # Auth Use Cases
    def get_login_use_case(self, session: AsyncSession) -> LoginUseCase:
        return LoginUseCase(user_repo=self.get_user_repo(session))

    def get_refresh_token_use_case(self, session: AsyncSession) -> RefreshTokenUseCase:
        return RefreshTokenUseCase(user_repo=self.get_user_repo(session))

    # Instruments Use Cases
    def get_list_instruments_use_case(self, session: AsyncSession) -> ListInstrumentsUseCase:
        return ListInstrumentsUseCase(
            instrument_repo=self.get_instrument_repo(session),
            exchange_repo=self.get_exchange_repo(session),
        )

    def get_sync_instruments_use_case(self, session: AsyncSession) -> SyncInstrumentsUseCase:
        return SyncInstrumentsUseCase(
            instrument_repo=self.get_instrument_repo(session),
            exchange_repo=self.get_exchange_repo(session),
            watchlist_repo=self.get_watchlist_repo(session),
            bracket_repo=self.get_bracket_repo(session),
            credential_repo=self.get_trading_credential_repo(session),
            account_repo=self.get_trading_account_repo(session),
            exchange_gateway=self.exchange_gateway,
        )

    # Watchlist Use Cases
    def get_get_watchlist_use_case(self, session: AsyncSession) -> GetWatchlistUseCase:
        return GetWatchlistUseCase(watchlist_repo=self.get_watchlist_repo(session))

    def get_toggle_watchlist_use_case(self, session: AsyncSession) -> ToggleWatchlistUseCase:
        return ToggleWatchlistUseCase(
            watchlist_repo=self.get_watchlist_repo(session),
            instrument_repo=self.get_instrument_repo(session),
            sync_instruments_use_case=self.get_sync_instruments_use_case(session),
        )


    # Providers Use Cases
    def get_list_providers_use_case(self, session: AsyncSession) -> ListProvidersUseCase:
        return ListProvidersUseCase(provider_repo=self.get_signal_provider_repo(session))

    def get_create_provider_use_case(self, session: AsyncSession) -> CreateProviderUseCase:
        return CreateProviderUseCase(provider_repo=self.get_signal_provider_repo(session))

    def get_get_provider_performance_use_case(self, session: AsyncSession) -> GetProviderPerformanceUseCase:
        return GetProviderPerformanceUseCase(provider_repo=self.get_signal_provider_repo(session))

    # Strategies Use Cases
    def get_list_strategies_use_case(self, session: AsyncSession) -> ListStrategiesUseCase:
        return ListStrategiesUseCase(strategy_repo=self.get_strategy_repo(session))

    def get_update_strategy_use_case(self, session: AsyncSession) -> UpdateStrategyUseCase:
        return UpdateStrategyUseCase(strategy_repo=self.get_strategy_repo(session))

    # Reports Use Cases
    def get_export_trades_csv_use_case(self, session: AsyncSession) -> ExportTradesCsvUseCase:
        return ExportTradesCsvUseCase(trade_repo=self.get_trade_repo(session))

    # Logs Use Cases
    def get_get_logs_use_case(self, session: AsyncSession) -> GetLogsUseCase:
        return GetLogsUseCase(log_repo=self.get_bot_log_repo(session))




    # -------------------------------------------------------------------------
    # Lifecycle Management
    # -------------------------------------------------------------------------
    async def init_resources(self) -> None:
        """Initialize singletons, connections, and event handlers on app startup."""
        async with self._lock:
            if self._is_initialized:
                return
            logger.info("Initializing ApplicationContainer resources...")

            # 1. Register Domain Event Listeners
            self.event_publisher.subscribe(TradeOpenedEvent, self.trade_notification_handler.on_trade_opened)
            self.event_publisher.subscribe(TradeWaitingEntryEvent, self.trade_notification_handler.on_trade_waiting_entry)
            self.event_publisher.subscribe(TradePartiallyClosedEvent, self.trade_notification_handler.on_trade_partially_closed)
            self.event_publisher.subscribe(StopLossMovedEvent, self.trade_notification_handler.on_stop_loss_moved)
            self.event_publisher.subscribe(TradeClosedEvent, self.trade_notification_handler.on_trade_closed)

            # 2. Pre-warm CCXT REST client
            try:
                await self.binance_connector.get_rest_exchange()
            except Exception as exc:
                logger.warning("Could not pre-initialize Binance exchange: %s", exc)

            self._is_initialized = True
            self.running = True
            if self.scheduler is None:
                self.scheduler = MagicMock()
            logger.info("ApplicationContainer successfully initialized.")

    async def shutdown_resources(self) -> None:
        """Gracefully release all active connections, background tasks, and sessions."""
        async with self._lock:
            if not self._is_initialized and not self.running:
                return
            logger.info("Shutting down ApplicationContainer resources...")

            # 1. Close Binance client sessions
            await self.exchange_gateway.close()

            # 2. Close Telegram client sessions
            await self.notification_gateway.close()

            # 3. Clear event publisher listeners
            self.event_publisher.clear()

            # 4. Dispose database engine pool
            await self._engine.dispose()

            self._is_initialized = False
            self.running = False
            logger.info("ApplicationContainer resources released.")

    async def initialize(self) -> None:
        """Alias for init_resources."""
        await self.init_resources()

    async def start_background_runners(self) -> None:
        """Start background runners."""
        self.running = True
        if self.scheduler is None:
            self.scheduler = MagicMock()

    async def shutdown(self) -> None:
        """Alias for shutdown_resources."""
        await self.shutdown_resources()


# Global default container instance
container = ApplicationContainer()


def get_container() -> ApplicationContainer:
    """Provide the global DI container instance."""
    return container
