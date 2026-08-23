"""API routers package."""

from src.api.routers.auth import router as auth_router
from src.api.routers.analytics import router as analytics_router

__all__ = ["auth_router", "analytics_router"]

