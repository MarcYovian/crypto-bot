"""FastAPI application factory and middleware configuration."""

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

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


def create_app() -> FastAPI:
    """Create and configure the FastAPI web application instance."""
    app = FastAPI(
        title="SMC CryptoBot Dashboard API",
        version="2.0.0",
        description="REST and WebSocket API for Binance Futures Semi-Automated Trading Bot Dashboard.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Configure CORS for frontend dashboard (Next.js / Vite / React)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, configure specific frontend domains
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Custom Exception Handlers for consistent API error schemas
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        message = errors[0].get("msg", "Validation error") if errors else "Invalid request body"
        field = " -> ".join(str(loc) for loc in errors[0].get("loc", [])) if errors else "payload"
        return JSONResponse(
            status_code=422,
            content={
                "detail": f"{field}: {message}",
                "code": "VALIDATION_ERROR",
                "errors": errors,
            },
        )

    # Include Routers
    app.include_router(auth_router)
    app.include_router(analytics_router)
    app.include_router(trades_router)
    app.include_router(signals_router)
    app.include_router(watchlist_router)
    app.include_router(instruments_router)
    app.include_router(providers_router)
    app.include_router(strategies_router)
    app.include_router(calculator_router)
    app.include_router(bot_router)
    app.include_router(settings_router)

    # Healthcheck Route
    @app.get("/health", tags=["Health"], summary="API Service Health Check")
    async def health_check() -> dict:
        return {"status": "ok", "service": "crypto-bot-api", "version": "2.0.0"}

    return app
