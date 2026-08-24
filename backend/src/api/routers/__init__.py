"""API routers package."""

from src.api.routers.auth import router as auth_router
from src.api.routers.analytics import router as analytics_router
from src.api.routers.trades import router as trades_router
from src.api.routers.signals import router as signals_router
from src.api.routers.watchlist import router as watchlist_router
from src.api.routers.instruments import router as instruments_router
from src.api.routers.providers import router as providers_router
from src.api.routers.strategies import router as strategies_router
from src.api.routers.calculator import router as calculator_router
from src.api.routers.bot import router as bot_router
from src.api.routers.settings import router as settings_router

__all__ = [
    "auth_router",
    "analytics_router",
    "trades_router",
    "signals_router",
    "watchlist_router",
    "instruments_router",
    "providers_router",
    "strategies_router",
    "calculator_router",
    "bot_router",
    "settings_router",
]


