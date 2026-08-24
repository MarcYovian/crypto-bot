"""FastAPI dependency injection providers for database sessions, security, and repositories."""

from typing import AsyncGenerator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from src.database.connection import AsyncSessionLocal
from src.database.models.users import User
from src.repository.user_repository import UserRepository
from src.repository.instrument_repository import InstrumentRepository
from src.repository.watchlist_repository import WatchlistRepository
from src.repository.trade_repository import TradeRepository
from src.repository.trade_risk_repository import TradeRiskRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.order_repository import OrderRepository
from src.repository.execution_repository import ExecutionRepository
from src.repository.trade_event_repository import TradeEventRepository
from src.repository.signal_repository import SignalRepository
from src.repository.signal_provider_repository import SignalProviderRepository
from src.repository.strategy_repository import StrategyRepository
from src.repository.trade_summary_repository import TradeSummaryRepository
from src.repository.exchange_repository import ExchangeRepository
from src.repository.instrument_leverage_bracket_repository import InstrumentLeverageBracketRepository
from src.repository.bot_setting_repository import BotSettingRepository
from src.repository.risk_profile_repository import RiskProfileRepository
from src.repository.trading_credential_repository import TradingCredentialRepository
from src.repository.trading_account_repository import TradingAccountRepository
from src.services.auth_service import AuthService
from src.services.analytics_service import AnalyticsService
from src.services.trade_service import TradeService
from src.services.position_manager import PositionManager
from src.services.signal_service import SignalService
from src.services.watchlist_service import WatchlistService
from src.services.instrument_service import InstrumentService
from src.services.provider_service import ProviderService
from src.services.strategy_service import StrategyService
from src.services.risk_calculator import RiskCalculatorService
from src.services.bot_service import BotService
from src.clients.binance_client import BinanceRestClient
from src.utils.security import decode_token
from src.utils.cache import in_memory_cache, AsyncInMemoryCache

security_bearer = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an asynchronous database session for FastAPI request context."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_cache() -> AsyncInMemoryCache:
    """Provide the global in-memory cache singleton instance."""
    return in_memory_cache


def get_user_repo(session: AsyncSession = Depends(get_db_session)) -> UserRepository:
    """Provide UserRepository instance bound to the request's database session."""
    return UserRepository(session)


def get_auth_service(session: AsyncSession = Depends(get_db_session)) -> AuthService:
    """Provide AuthService instance bound to the request's database session."""
    return AuthService(user_repo=UserRepository(session))


def get_analytics_service(session: AsyncSession = Depends(get_db_session)) -> AnalyticsService:
    """Provide AnalyticsService instance bound to the request's database session."""
    return AnalyticsService(
        daily_risk_repo=DailyRiskRepository(session),
        trade_summary_repo=TradeSummaryRepository(session),
        trade_repo=TradeRepository(session),
    )


def get_trade_service(session: AsyncSession = Depends(get_db_session)) -> TradeService:
    """Provide TradeService instance bound to the request's database session."""
    return TradeService(
        instrument_repo=InstrumentRepository(session),
        watchlist_repo=WatchlistRepository(session),
        trade_repo=TradeRepository(session),
        trade_risk_repo=TradeRiskRepository(session),
        daily_risk_repo=DailyRiskRepository(session),
        order_repo=OrderRepository(session),
        trade_event_repo=TradeEventRepository(session),
    )


def get_position_manager(session: AsyncSession = Depends(get_db_session)) -> PositionManager:
    """Provide PositionManager instance bound to the request's database session."""
    return PositionManager(
        trade_repo=TradeRepository(session),
        order_repo=OrderRepository(session),
        execution_repo=ExecutionRepository(session),
        trade_event_repo=TradeEventRepository(session),
        trade_summary_repo=TradeSummaryRepository(session),
        daily_risk_repo=DailyRiskRepository(session),
    )


def get_signal_service(session: AsyncSession = Depends(get_db_session)) -> SignalService:
    """Provide SignalService instance bound to the request's database session."""
    signal_repo = SignalRepository(session)
    instrument_repo = InstrumentRepository(session)
    trade_service = TradeService(
        instrument_repo=instrument_repo,
        watchlist_repo=WatchlistRepository(session),
        trade_repo=TradeRepository(session),
        trade_risk_repo=TradeRiskRepository(session),
        daily_risk_repo=DailyRiskRepository(session),
        order_repo=OrderRepository(session),
        trade_event_repo=TradeEventRepository(session),
    )
    return SignalService(
        signal_repo=signal_repo,
        trade_service=trade_service,
        instrument_repo=instrument_repo,
    )


def get_instrument_service(session: AsyncSession = Depends(get_db_session)) -> InstrumentService:
    """Provide InstrumentService instance bound to the request's database session."""
    return InstrumentService(
        instrument_repo=InstrumentRepository(session),
        exchange_repo=ExchangeRepository(session),
        watchlist_repo=WatchlistRepository(session),
        bracket_repo=InstrumentLeverageBracketRepository(session),
        binance_client=BinanceRestClient(),
    )


def get_watchlist_service(session: AsyncSession = Depends(get_db_session)) -> WatchlistService:
    """Provide WatchlistService instance bound to the request's database session."""
    inst_repo = InstrumentRepository(session)
    inst_service = InstrumentService(
        instrument_repo=inst_repo,
        exchange_repo=ExchangeRepository(session),
        watchlist_repo=WatchlistRepository(session),
        bracket_repo=InstrumentLeverageBracketRepository(session),
        binance_client=BinanceRestClient(),
    )
    return WatchlistService(
        watchlist_repo=WatchlistRepository(session),
        instrument_repo=inst_repo,
        instrument_service=inst_service,
    )


def get_provider_service(session: AsyncSession = Depends(get_db_session)) -> ProviderService:
    """Provide ProviderService instance bound to the request's database session."""
    return ProviderService(provider_repo=SignalProviderRepository(session))


def get_strategy_service(session: AsyncSession = Depends(get_db_session)) -> StrategyService:
    """Provide StrategyService instance bound to the request's database session."""
    return StrategyService(strategy_repo=StrategyRepository(session))


def get_risk_calculator_service(session: AsyncSession = Depends(get_db_session)) -> RiskCalculatorService:
    """Provide RiskCalculatorService instance bound with InstrumentRepository for live simulations."""
    return RiskCalculatorService(instrument_repo=InstrumentRepository(session))


def get_bot_service(session: AsyncSession = Depends(get_db_session)) -> BotService:
    """Provide BotService instance configured with necessary database repositories."""
    return BotService(
        bot_setting_repo=BotSettingRepository(session),
        risk_profile_repo=RiskProfileRepository(session),
        trade_repo=TradeRepository(session),
        order_repo=OrderRepository(session),
        credential_repo=TradingCredentialRepository(session),
        account_repo=TradingAccountRepository(session),
        exchange_repo=ExchangeRepository(session),
    )






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

