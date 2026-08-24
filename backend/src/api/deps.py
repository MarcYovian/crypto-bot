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
from src.repository.trade_summary_repository import TradeSummaryRepository
from src.services.auth_service import AuthService
from src.services.analytics_service import AnalyticsService
from src.services.trade_service import TradeService
from src.services.position_manager import PositionManager
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
