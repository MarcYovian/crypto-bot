"""FastAPI dependency injection providers for database sessions, security, and repositories."""

from typing import AsyncGenerator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from src.infrastructure.persistence.connection import AsyncSessionLocal
from src.infrastructure.persistence.models.users import User
from src.infrastructure.persistence.repositories.user_repository import UserRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.watchlist_repository import WatchlistRepository
from src.infrastructure.persistence.repositories.trade_repository import TradeRepository
from src.infrastructure.persistence.repositories.trade_risk_repository import TradeRiskRepository
from src.infrastructure.persistence.repositories.daily_risk_repository import DailyRiskRepository
from src.infrastructure.persistence.repositories.order_repository import OrderRepository
from src.infrastructure.persistence.repositories.execution_repository import ExecutionRepository
from src.infrastructure.persistence.repositories.trade_event_repository import TradeEventRepository
from src.infrastructure.persistence.repositories.signal_repository import SignalRepository
from src.infrastructure.persistence.repositories.signal_provider_repository import SignalProviderRepository
from src.infrastructure.persistence.repositories.strategy_repository import StrategyRepository
from src.infrastructure.persistence.repositories.trade_summary_repository import TradeSummaryRepository
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository
from src.infrastructure.persistence.repositories.instrument_leverage_bracket_repository import InstrumentLeverageBracketRepository
from src.infrastructure.persistence.repositories.bot_setting_repository import BotSettingRepository
from src.infrastructure.persistence.repositories.risk_profile_repository import RiskProfileRepository
from src.infrastructure.persistence.repositories.trading_credential_repository import TradingCredentialRepository
from src.infrastructure.persistence.repositories.trading_account_repository import TradingAccountRepository
from src.utils.security import decode_token

from src.utils.cache import in_memory_cache, AsyncInMemoryCache

from src.infrastructure.di.container import container, ApplicationContainer, get_container
from src.domain.ports.gateways import IExchangeGateway, INotificationGateway
from src.domain.ports.event_publisher import IDomainEventPublisher

security_bearer = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an asynchronous database session for FastAPI request context."""
    async with container.session_scope() as session:
        yield session


def get_cache() -> AsyncInMemoryCache:
    """Provide the global in-memory cache singleton instance."""
    return in_memory_cache


def get_exchange_gateway(
    app_container: ApplicationContainer = Depends(get_container),
) -> IExchangeGateway:
    """Provide the IExchangeGateway adapter singleton."""
    return app_container.exchange_gateway


def get_notification_gateway(
    app_container: ApplicationContainer = Depends(get_container),
) -> INotificationGateway:
    """Provide the INotificationGateway adapter singleton."""
    return app_container.notification_gateway


def get_event_publisher(
    app_container: ApplicationContainer = Depends(get_container),
) -> IDomainEventPublisher:
    """Provide the IDomainEventPublisher bus singleton."""
    return app_container.event_publisher



def get_user_repo(session: AsyncSession = Depends(get_db_session)) -> UserRepository:
    """Provide UserRepository instance bound to the request's database session."""
    return UserRepository(session)


# =============================================================================
# CLEAN ARCHITECTURE APPLICATION USE CASES
# =============================================================================


from src.application.use_cases.trades import (
    ExecuteSignalUseCase,
    HandleOrderFillUseCase,
    CloseTradeUseCase,
    UpdateStopLossUseCase,
    SyncPositionsUseCase,
    GetActiveTradesUseCase,
    GetTradeHistoryUseCase,
    GetTradeDetailUseCase,
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




def get_execute_signal_use_case(session: AsyncSession = Depends(get_db_session)) -> ExecuteSignalUseCase:
    """Provide ExecuteSignalUseCase instance resolved from DI container."""
    return container.get_execute_signal_use_case(session)


def get_handle_order_fill_use_case(session: AsyncSession = Depends(get_db_session)) -> HandleOrderFillUseCase:
    """Provide HandleOrderFillUseCase instance resolved from DI container."""
    return container.get_handle_order_fill_use_case(session)


def get_close_trade_use_case(session: AsyncSession = Depends(get_db_session)) -> CloseTradeUseCase:
    """Provide CloseTradeUseCase instance resolved from DI container."""
    return container.get_close_trade_use_case(session)


def get_update_stop_loss_use_case(session: AsyncSession = Depends(get_db_session)) -> UpdateStopLossUseCase:
    """Provide UpdateStopLossUseCase instance resolved from DI container."""
    return container.get_update_stop_loss_use_case(session)


def get_sync_positions_use_case(session: AsyncSession = Depends(get_db_session)) -> SyncPositionsUseCase:
    """Provide SyncPositionsUseCase instance resolved from DI container."""
    return container.get_sync_positions_use_case(session)


def get_simulate_risk_use_case(session: AsyncSession = Depends(get_db_session)) -> SimulateRiskUseCase:
    """Provide SimulateRiskUseCase instance resolved from DI container."""
    return container.get_simulate_risk_use_case(session)


def get_check_daily_risk_use_case(session: AsyncSession = Depends(get_db_session)) -> CheckDailyRiskUseCase:
    """Provide CheckDailyRiskUseCase instance resolved from DI container."""
    return container.get_check_daily_risk_use_case(session)


def get_parse_signal_use_case(session: AsyncSession = Depends(get_db_session)) -> ParseSignalUseCase:
    """Provide ParseSignalUseCase instance resolved from DI container."""
    return container.get_parse_signal_use_case(session)


def get_approve_signal_use_case(session: AsyncSession = Depends(get_db_session)) -> ApproveSignalUseCase:
    """Provide ApproveSignalUseCase instance resolved from DI container."""
    return container.get_approve_signal_use_case(session)


def get_reject_signal_use_case(session: AsyncSession = Depends(get_db_session)) -> RejectSignalUseCase:
    """Provide RejectSignalUseCase instance resolved from DI container."""
    return container.get_reject_signal_use_case(session)


def get_handle_command_use_case(session: AsyncSession = Depends(get_db_session)) -> HandleTelegramCommandUseCase:
    """Provide HandleTelegramCommandUseCase instance resolved from DI container."""
    return container.get_handle_command_use_case(session)


def get_active_trades_use_case(session: AsyncSession = Depends(get_db_session)) -> GetActiveTradesUseCase:
    """Provide GetActiveTradesUseCase instance resolved from DI container."""
    return container.get_get_active_trades_use_case(session)


def get_trade_history_use_case(session: AsyncSession = Depends(get_db_session)) -> GetTradeHistoryUseCase:
    """Provide GetTradeHistoryUseCase instance resolved from DI container."""
    return container.get_get_trade_history_use_case(session)


def get_trade_detail_use_case(session: AsyncSession = Depends(get_db_session)) -> GetTradeDetailUseCase:
    """Provide GetTradeDetailUseCase instance resolved from DI container."""
    return container.get_get_trade_detail_use_case(session)


def get_signals_feed_use_case(session: AsyncSession = Depends(get_db_session)) -> GetSignalsFeedUseCase:
    """Provide GetSignalsFeedUseCase instance resolved from DI container."""
    return container.get_get_signals_feed_use_case(session)


def get_manual_execute_signal_use_case(session: AsyncSession = Depends(get_db_session)) -> ManualExecuteSignalUseCase:
    """Provide ManualExecuteSignalUseCase instance resolved from DI container."""
    return container.get_manual_execute_signal_use_case(session)


# Bot & Settings Providers
def get_bot_status_use_case(session: AsyncSession = Depends(get_db_session)) -> GetBotStatusUseCase:
    return container.get_get_bot_status_use_case(session)


def get_pause_bot_use_case(session: AsyncSession = Depends(get_db_session)) -> PauseBotUseCase:
    return container.get_pause_bot_use_case(session)


def get_resume_bot_use_case(session: AsyncSession = Depends(get_db_session)) -> ResumeBotUseCase:
    return container.get_resume_bot_use_case(session)


def get_panic_close_use_case(session: AsyncSession = Depends(get_db_session)) -> PanicCloseUseCase:
    return container.get_panic_close_use_case(session)


def get_settings_use_case(session: AsyncSession = Depends(get_db_session)) -> GetSettingsUseCase:
    return container.get_get_settings_use_case(session)


def get_update_settings_use_case(session: AsyncSession = Depends(get_db_session)) -> UpdateSettingsUseCase:
    return container.get_update_settings_use_case(session)


def get_save_credentials_use_case(session: AsyncSession = Depends(get_db_session)) -> SaveCredentialsUseCase:
    return container.get_save_credentials_use_case(session)


# Analytics Providers
def get_dashboard_summary_use_case(session: AsyncSession = Depends(get_db_session)) -> GetDashboardSummaryUseCase:
    return container.get_get_dashboard_summary_use_case(session)


def get_equity_curve_use_case(session: AsyncSession = Depends(get_db_session)) -> GetEquityCurveUseCase:
    return container.get_get_equity_curve_use_case(session)


# Auth Providers
def get_login_use_case(session: AsyncSession = Depends(get_db_session)) -> LoginUseCase:
    return container.get_login_use_case(session)


def get_refresh_token_use_case(session: AsyncSession = Depends(get_db_session)) -> RefreshTokenUseCase:
    return container.get_refresh_token_use_case(session)


# Instruments Providers
def get_list_instruments_use_case(session: AsyncSession = Depends(get_db_session)) -> ListInstrumentsUseCase:
    return container.get_list_instruments_use_case(session)


def get_sync_instruments_use_case(session: AsyncSession = Depends(get_db_session)) -> SyncInstrumentsUseCase:
    return container.get_sync_instruments_use_case(session)


# Watchlist Providers
def get_watchlist_use_case(session: AsyncSession = Depends(get_db_session)) -> GetWatchlistUseCase:
    return container.get_get_watchlist_use_case(session)


def get_toggle_watchlist_use_case(session: AsyncSession = Depends(get_db_session)) -> ToggleWatchlistUseCase:
    return container.get_toggle_watchlist_use_case(session)


# Providers (Signal Providers) Providers
def get_list_providers_use_case(session: AsyncSession = Depends(get_db_session)) -> ListProvidersUseCase:
    return container.get_list_providers_use_case(session)


def get_create_provider_use_case(session: AsyncSession = Depends(get_db_session)) -> CreateProviderUseCase:
    return container.get_create_provider_use_case(session)


def get_provider_performance_use_case(session: AsyncSession = Depends(get_db_session)) -> GetProviderPerformanceUseCase:
    return container.get_get_provider_performance_use_case(session)


# Strategies Providers
def get_list_strategies_use_case(session: AsyncSession = Depends(get_db_session)) -> ListStrategiesUseCase:
    return container.get_list_strategies_use_case(session)


def get_update_strategy_use_case(session: AsyncSession = Depends(get_db_session)) -> UpdateStrategyUseCase:
    return container.get_update_strategy_use_case(session)


# Reports Providers
def get_export_trades_csv_use_case(session: AsyncSession = Depends(get_db_session)) -> ExportTradesCsvUseCase:
    return container.get_export_trades_csv_use_case(session)


# Logs Providers
def get_logs_use_case(session: AsyncSession = Depends(get_db_session)) -> GetLogsUseCase:
    return container.get_get_logs_use_case(session)









async def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    user_repo: UserRepository = Depends(get_user_repo),
) -> User:
    """Extract, decode, and validate the JWT Bearer token to retrieve the authenticated User entity."""
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth.credentials
    try:
        payload = decode_token(token)
        username: Optional[str] = payload.get("sub")
        token_type: Optional[str] = payload.get("type")

        if username is None or token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload or token type.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please refresh your token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await user_repo.get_by_username(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with this token no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    return user


async def require_admin_role(current_user: User = Depends(get_current_user)) -> User:
    """Enforce that the authenticated user possesses the ADMIN role."""
    if current_user.role.upper() != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Admin role required.",
        )
    return current_user


# Backward-compatible alias
get_current_admin_user = require_admin_role


def get_scheduler_runner():
    """FastAPI dependency providing the active SchedulerService instance."""
    from src.infrastructure.bootstrap import get_scheduler_service
    return get_scheduler_service()

